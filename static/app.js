let ws = null;
let currentRole = "";
let clientName = "";
let currentBid = 0;
let basePrice = 0;

// Format money helper: formats absolute rupees in Lakhs/Crores
function formatRupees(amount) {
    if (!amount || amount <= 0) return "₹0";
    if (amount >= 10000000) { // 1 Crore
        return `₹${(amount / 10000000).toFixed(2)} Cr`;
    }
    return `₹${(amount / 100000).toFixed(0)} Lakh`;
}

// Client-side mapping of the increment rules
function getNextIncrement(bid) {
    if (bid < 10000000) { // Below 1 Crore
        return 1000000;    // 10 Lakhs
    } else if (bid < 50000000) { // 1 to 5 Crore
        return 2500000;    // 25 Lakhs
    } else if (bid < 100000000) { // 5 to 10 Crore
        return 5000000;    // 50 Lakhs
    } else if (bid < 200000000) { // 10 to 20 Crore
        return 10000000;   // 1 Crore
    } else { // Above 20 Crore
        return 20000000;   // 2 Crore
    }
}

// Audio indicators for rich responsive feedback
const hammerAudio = new Audio('https://assets.mixkit.co/active_storage/sfx/2568/2568-84.wav'); // Hammer/gavel sound
const bidAudio = new Audio('https://assets.mixkit.co/active_storage/sfx/2019/2019-84.wav');   // Digital click

function playSound(type) {
    try {
        if (type === 'bid') {
            bidAudio.currentTime = 0;
            bidAudio.play();
        } else if (type === 'hammer') {
            hammerAudio.currentTime = 0;
            hammerAudio.play();
        }
    } catch (e) {
        console.log("Audio play blocked by browser policies.");
    }
}

// Toggle Join Page fields
const roleSelect = document.getElementById("role-select");
const teamNameGroup = document.getElementById("team-name-group");
const teamNameInput = document.getElementById("team-name-input");

roleSelect.addEventListener("change", () => {
    if (roleSelect.value === "auctioneer") {
        teamNameGroup.style.display = "none";
    } else {
        teamNameGroup.style.display = "block";
    }
});

// Join Button Trigger
const joinBtn = document.getElementById("join-btn");
joinBtn.addEventListener("click", () => {
    currentRole = roleSelect.value;
    clientName = currentRole === "auctioneer" ? "Auctioneer" : teamNameInput.value.trim();

    if (currentRole === "team" && !clientName) {
        alert("Please enter a valid Team Name.");
        return;
    }

    initializeWebSocket();
});

function initializeWebSocket() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = window.location.host;
    const url = `${protocol}//${host}/ws/${currentRole}/${encodeURIComponent(clientName)}`;

    ws = new WebSocket(url);

    ws.onopen = () => {
        // Swap Views
        document.getElementById("join-view").classList.remove("active");
        document.getElementById("connection-indicator").style.display = "block";

        if (currentRole === "team") {
            document.getElementById("owner-view").classList.add("active");
            document.getElementById("owner-assigned-team").innerText = clientName;
        } else {
            document.getElementById("auctioneer-view").classList.add("active");
        }
    };

    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        console.log("WebSocket event: ", data);

        if (data.type === "sync" || data.type === "state_change" || data.type === "bid_update") {
            const state = data.state;
            const history = data.history || [];

            // Play audio signals
            if (data.type === "bid_update") {
                playSound('bid');
            } else if (state.status === "sold" || state.status === "unsold") {
                playSound('hammer');
            }

            // Sync UI variables
            currentBid = state.current_bid;
            basePrice = state.base_price;

            // Render common components
            updateUIRoleSpecific(state, history);
        }

        if (data.type === "online_update" || data.type === "sync") {
            const onlineTeams = data.online_teams || [];
            document.getElementById("online-users-count").innerText = `Online Owners: ${onlineTeams.length}`;
        }
    };

    ws.onclose = () => {
        alert("Disconnected from auction server. Attempting reconnect...");
        setTimeout(initializeWebSocket, 3000);
    };

    ws.onerror = (err) => {
        console.error("Socket error: ", err);
    };
}

function updateUIRoleSpecific(state, history) {
    const formattedBase = formatRupees(state.base_price);
    const formattedCurrent = formatRupees(state.current_bid);
    const bidder = state.highest_bidder || "None";
    const statusText = state.status.toUpperCase();

    // Map correct increment display
    const increment = getNextIncrement(state.current_bid);
    const formattedInc = `+${formatRupees(increment)}`;

    // Build the bid history element items
    let historyHTML = "";
    history.forEach((bid, index) => {
        const isFirst = index === 0 ? "first" : "";
        historyHTML += `
            <li class="history-item ${isFirst}">
                <span class="history-team">${bid.team_name}</span>
                <span class="history-amount">${formatRupees(bid.bid_amount)}</span>
            </li>
        `;
    });

    if (currentRole === "team") {
        // Update labels
        document.getElementById("owner-player-name").innerText = state.player_name || "NO PLAYER ACTIVE";
        document.getElementById("owner-base-price").innerText = formattedBase;
        document.getElementById("owner-current-bid").innerText = formattedCurrent;
        document.getElementById("owner-highest-bidder").innerText = bidder;
        document.getElementById("owner-bid-history-list").innerHTML = historyHTML;

        // Status badge
        const badge = document.getElementById("owner-auction-status-badge");
        badge.innerText = statusText;
        badge.className = `status-badge status-${state.status}`;

        // Fixed Bid button setup
        const bidBtn = document.getElementById("owner-bid-btn");
        const nextPrice = state.current_bid === 0 ? state.base_price : state.current_bid + increment;
        
        bidBtn.innerText = `BID ${formatRupees(nextPrice)}`;
        
        // Show next increment label
        document.getElementById("owner-increment-info").innerHTML = `Next Increment: <span>${formattedInc}</span>`;

        // Interactive button state
        // Enable only if status is bidding and the current client isn't already the highest bidder
        if (state.status === "bidding" && bidder !== clientName) {
            bidBtn.disabled = false;
        } else {
            bidBtn.disabled = true;
        }
    } else if (currentRole === "auctioneer") {
        // Update labels
        document.getElementById("auc-current-bid").innerText = formattedCurrent;
        document.getElementById("auc-highest-bidder").innerText = bidder;
        document.getElementById("auc-bid-history-list").innerHTML = historyHTML;

        // Status badge
        const badge = document.getElementById("auc-auction-status-badge");
        badge.innerText = statusText;
        badge.className = `status-badge status-${state.status}`;

        // Button enabling / disabling
        const startBtn = document.getElementById("auc-start-btn");
        const soldBtn = document.getElementById("auc-sold-btn");
        const unsoldBtn = document.getElementById("auc-unsold-btn");

        if (state.status === "bidding") {
            startBtn.disabled = true;
            unsoldBtn.disabled = false;
            // Can sell only if there is a bid
            soldBtn.disabled = state.current_bid <= 0;
        } else {
            startBtn.disabled = false;
            soldBtn.disabled = true;
            unsoldBtn.disabled = true;
        }
    }
}

// Bidding interactions
const ownerBidBtn = document.getElementById("owner-bid-btn");
ownerBidBtn.addEventListener("click", () => {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ action: "place_bid" }));
    }
});

// Auctioneer Actions
const startBtn = document.getElementById("auc-start-btn");
startBtn.addEventListener("click", () => {
    const pName = document.getElementById("auc-player-name-input").value.trim();
    const basePriceLakhs = parseInt(document.getElementById("auc-base-price-input").value);
    
    if (!pName) {
        alert("Please enter a Player Name first.");
        return;
    }

    // Convert Lakhs to absolute Rupees
    const basePriceRupees = basePriceLakhs * 100000;

    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
            action: "start_auction",
            player_name: pName,
            base_price: basePriceRupees
        }));
    }
});

const soldBtn = document.getElementById("auc-sold-btn");
soldBtn.addEventListener("click", () => {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ action: "sold" }));
    }
});

const unsoldBtn = document.getElementById("auc-unsold-btn");
unsoldBtn.addEventListener("click", () => {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ action: "unsold" }));
    }
});

const resetBtn = document.getElementById("auc-reset-btn");
resetBtn.addEventListener("click", () => {
    // Clear the input fields for next player
    document.getElementById("auc-player-name-input").value = "";
    document.getElementById("auc-base-price-input").selectedIndex = 0;
    
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ action: "reset" }));
    }
});
