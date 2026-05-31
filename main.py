import csv
import io
from typing import Dict, List, Set
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import database

app = FastAPI(title="IPL Real-Time Auction")

# Initialize SQLite database on startup
database.init_db()

# Mount static folder
app.mount("/static", StaticFiles(directory="static"), name="static")

# Helper function to compute next bid increment
def get_next_increment(current_bid: int) -> int:
    if current_bid < 1_00_00_000: # < 1 Crore
        return 10_00_000          # 10 Lakhs
    elif current_bid < 5_00_00_000: # 1 Crore to 5 Crore
        return 25_00_000          # 25 Lakhs
    elif current_bid < 10_00_00_000: # 5 Crore to 10 Crore
        return 50_00_000          # 50 Lakhs
    elif current_bid < 20_00_00_000: # 10 Crore to 20 Crore
        return 1_00_00_000         # 1 Crore
    else:                          # Above 20 Crore
        return 2_00_00_000         # 2 Crore

class ConnectionManager:
    def __init__(self):
        # Maps user session keys to WebSocket connections
        # e.g., "auctioneer" or team name -> WebSocket
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, client_id: str, websocket: WebSocket):
        await websocket.accept()
        # If client_id is already connected, close the old one to allow reconnects
        if client_id in self.active_connections:
            try:
                await self.active_connections[client_id].close()
            except Exception:
                pass
        self.active_connections[client_id] = websocket

    def disconnect(self, client_id: str):
        if client_id in self.active_connections:
            del self.active_connections[client_id]

    async def broadcast(self, message: dict):
        for client_id, connection in list(self.active_connections.items()):
            try:
                await connection.send_json(message)
            except Exception:
                # If sending fails, clean up connection
                self.disconnect(client_id)

manager = ConnectionManager()

@app.get("/")
def get_index():
    # Return index.html from static folder
    with open("static/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

@app.get("/export-csv")
def export_csv():
    sold_players = database.get_all_sold_players()
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow(["Player Name", "Base Price (₹)", "Sold Price (₹)", "Sold Price (Text)", "Winning Team", "Timestamp"])
    
    # Helper to convert to Lakhs/Crores for text representation in CSV
    def format_rupees_text(amount: int) -> str:
        if amount >= 1_00_00_000:
            return f"₹{amount / 1_00_00_000:.2f} Cr"
        return f"₹{amount / 100_000:.0f} Lakh"

    for p in sold_players:
        writer.writerow([
            p["player_name"],
            p["base_price"],
            p["sold_price"],
            format_rupees_text(p["sold_price"]),
            p["team_name"],
            p["timestamp"]
        ])
    
    response = Response(content=output.getvalue(), media_type="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=ipl_auction_results.csv"
    return response

@app.websocket("/ws/{role}/{client_name}")
async def websocket_endpoint(websocket: WebSocket, role: str, client_name: str):
    # Normalize client identifier
    # Auctioneer uses "auctioneer", Team Owner uses their entered team name
    client_id = "auctioneer" if role == "auctioneer" else f"team_{client_name}"
    
    await manager.connect(client_id, websocket)
    
    # Send current state on connection
    state = database.get_auction_state()
    history = database.get_bid_history(state["player_name"]) if state["player_name"] else []
    
    # Broadcast current online teams
    online_teams = [k.replace("team_", "") for k in manager.active_connections.keys() if k.startswith("team_")]
    
    await websocket.send_json({
        "type": "sync",
        "state": state,
        "history": history,
        "online_teams": online_teams,
        "your_role": role,
        "your_name": client_name
    })
    
    # Broadcast updated list of online teams to everyone
    await manager.broadcast({
        "type": "online_update",
        "online_teams": online_teams
    })
    
    try:
        while True:
            data = await websocket.receive_json()
            
            # Action Handlers
            action = data.get("action")
            
            if action == "start_auction":
                if role != "auctioneer":
                    continue
                p_name = data.get("player_name", "").strip()
                b_price = int(data.get("base_price", 0))
                if p_name and b_price >= 0:
                    database.update_auction_state(p_name, b_price, 0, "", "bidding")
                    # Clear history for this player by adding state to database
                    # Send sync
                    state = database.get_auction_state()
                    await manager.broadcast({
                        "type": "state_change",
                        "state": state,
                        "history": []
                    })
                    
            elif action == "place_bid":
                if role != "team":
                    continue
                
                # Fetch active state
                state = database.get_auction_state()
                if state["status"] != "bidding":
                    continue
                
                # Calculate next bid amount
                if state["current_bid"] == 0:
                    next_bid = state["base_price"]
                else:
                    next_bid = state["current_bid"] + get_next_increment(state["current_bid"])
                
                # Update DB state with new bid and bidder
                database.update_auction_state(
                    state["player_name"],
                    state["base_price"],
                    next_bid,
                    client_name,
                    "bidding"
                )
                
                # Record bid history
                database.add_bid(state["player_name"], next_bid, client_name)
                
                # Fetch updated data
                updated_state = database.get_auction_state()
                updated_history = database.get_bid_history(state["player_name"])
                
                # Broadcast real-time update
                await manager.broadcast({
                    "type": "bid_update",
                    "state": updated_state,
                    "history": updated_history
                })
                
            elif action == "sold":
                if role != "auctioneer":
                    continue
                state = database.get_auction_state()
                if state["status"] == "bidding" and state["current_bid"] > 0:
                    database.mark_as_sold(
                        state["player_name"],
                        state["base_price"],
                        state["current_bid"],
                        state["highest_bidder"]
                    )
                    updated_state = database.get_auction_state()
                    await manager.broadcast({
                        "type": "state_change",
                        "state": updated_state,
                        "history": database.get_bid_history(state["player_name"])
                    })
                    
            elif action == "unsold":
                if role != "auctioneer":
                    continue
                state = database.get_auction_state()
                if state["status"] == "bidding":
                    database.mark_as_unsold(state["player_name"], state["base_price"])
                    updated_state = database.get_auction_state()
                    await manager.broadcast({
                        "type": "state_change",
                        "state": updated_state,
                        "history": database.get_bid_history(state["player_name"])
                    })
                    
            elif action == "reset":
                if role != "auctioneer":
                    continue
                database.reset_auction()
                updated_state = database.get_auction_state()
                await manager.broadcast({
                    "type": "state_change",
                    "state": updated_state,
                    "history": []
                })
                
    except WebSocketDisconnect:
        manager.disconnect(client_id)
        online_teams = [k.replace("team_", "") for k in manager.active_connections.keys() if k.startswith("team_")]
        await manager.broadcast({
            "type": "online_update",
            "online_teams": online_teams
        })
