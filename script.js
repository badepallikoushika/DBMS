const API = "http://127.0.0.1:8000";

let products = [];
let warehouses = [];
let currentUser = null;

function formatCurrency(amount) {
    return "Rs. " + Number(amount || 0).toLocaleString("en-IN");
}

// Check session and setup user profile
function checkAuth() {
    const path = window.location.pathname.toLowerCase();
    const isLoginPage = path.endsWith("login.html");
    const userJson = localStorage.getItem("currentUser");

    if (!userJson && !isLoginPage) {
        window.location.href = "login.html";
        return null;
    }

    if (userJson) {
        try {
            currentUser = JSON.parse(userJson);
            renderUserProfile();
        } catch (e) {
            localStorage.removeItem("currentUser");
            if (!isLoginPage) window.location.href = "login.html";
        }
    }
    return currentUser;
}

function renderUserProfile() {
    const box = document.getElementById("userProfileBox");
    if (!box || !currentUser) return;

    const isAdmin = currentUser.role === "admin";
    box.innerHTML = `
        <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:4px;">
            <p style="margin:0; font-weight:bold; color:white;">${currentUser.name}</p>
            <span class="badge ${isAdmin ? 'primary' : 'success'}" style="font-size:10px; padding:2px 6px;">
                ${currentUser.role.toUpperCase()}
            </span>
        </div>
        <small style="color:#94a3b8;">${currentUser.email}</small>
    `;

    // Strict access control: hide admin-only elements if staff user
    if (!isAdmin) {
        document.querySelectorAll(".admin-only").forEach(el => el.style.display = "none");
    }
}

function logoutUser() {
    localStorage.removeItem("currentUser");
    window.location.href = "login.html";
}

async function apiGet(endpoint) {
    try {
        const response = await fetch(`${API}${endpoint}`);
        if (!response.ok) {
            const errData = await response.json().catch(() => ({}));
            throw new Error(errData.detail || `HTTP Error ${response.status}`);
        }
        return await response.json();
    } catch (error) {
        console.error(`API GET ${endpoint} failed:`, error);
        throw error;
    }
}

async function apiPost(endpoint, body) {
    try {
        const response = await fetch(`${API}${endpoint}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body)
        });
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.detail || data.error || `HTTP ${response.status}`);
        }
        return data;
    } catch (error) {
        console.error(`API POST ${endpoint} failed:`, error);
        throw error;
    }
}

async function apiPut(endpoint, body) {
    try {
        const response = await fetch(`${API}${endpoint}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body)
        });
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.detail || data.error || `HTTP ${response.status}`);
        }
        return data;
    } catch (error) {
        console.error(`API PUT ${endpoint} failed:`, error);
        throw error;
    }
}

async function apiDelete(endpoint) {
    try {
        const response = await fetch(`${API}${endpoint}`, { method: "DELETE" });
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.detail || `HTTP ${response.status}`);
        }
        return data;
    } catch (error) {
        console.error(`API DELETE ${endpoint} failed:`, error);
        throw error;
    }
}

// 1. DASHBOARD
async function initDashboard() {
    try {
        products = await apiGet("/products");
        warehouses = await apiGet("/warehouses");

        const totalProducts = products.length;
        const totalStock = products.reduce((sum, p) => sum + p.quantity, 0);
        const lowStock = products.filter(p => p.status === "LOW STOCK").length;
        const totalValuation = products.reduce((sum, p) => sum + (Number(p.price) * p.quantity), 0);

        const elTotalProducts = document.getElementById("totalProducts");
        const elTotalStock = document.getElementById("inStock");
        const elLowStock = document.getElementById("lowStock");
        const elValuation = document.getElementById("inventoryValue");

        if (elTotalProducts) elTotalProducts.textContent = totalProducts;
        if (elTotalStock) elTotalStock.textContent = totalStock;
        if (elLowStock) elLowStock.textContent = lowStock;
        if (elValuation) elValuation.textContent = formatCurrency(totalValuation);

        const recentTable = document.getElementById("recentProductsTable");
        if (recentTable) {
            if (products.length === 0) {
                recentTable.innerHTML = '<tr><td colspan="6" class="loading">No products found.</td></tr>';
            } else {
                recentTable.innerHTML = products.slice(0, 5).map(p => `
                    <tr>
                        <td>${p.id}</td>
                        <td><strong>${p.name}</strong></td>
                        <td>${p.sku}</td>
                        <td>${p.category}</td>
                        <td>${formatCurrency(p.price)}</td>
                        <td>
                            <span class="${p.status === 'LOW STOCK' ? 'low' : 'stock'}">
                                ${p.status} (${p.quantity} units)
                            </span>
                        </td>
                    </tr>
                `).join("");
            }
        }
    } catch (error) {
        console.error("Failed to load dashboard:", error);
        const summary = document.getElementById("dashboardSummary");
        if (summary) {
            summary.innerHTML = `
                <div class="alert-box show error">
                    <strong>Cannot connect to FastAPI backend at ${API}</strong><br>
                    Make sure the backend is running.
                </div>
            `;
        }
    }
}

// 2. INVENTORY
async function initInventory() {
    try {
        products = await apiGet("/products");
        warehouses = await apiGet("/warehouses");
        renderProductTable(products);
        setupInventoryFilters();
        setupAddProductForm();
    } catch (error) {
        console.error("Failed to load inventory:", error);
        const table = document.getElementById("productTable");
        if (table) {
            table.innerHTML = `<tr><td colspan="8" class="loading">Failed to connect to backend server.</td></tr>`;
        }
    }
}

function renderProductTable(items) {
    const table = document.getElementById("productTable");
    if (!table) return;

    if (items.length === 0) {
        table.innerHTML = `<tr><td colspan="8" class="loading">No products matching criteria.</td></tr>`;
        return;
    }

    const isAdmin = currentUser && currentUser.role === "admin";

    table.innerHTML = items.map(p => `
        <tr>
            <td>${p.id}</td>
            <td><strong>${p.name}</strong></td>
            <td>${p.sku}</td>
            <td><span class="badge primary">${p.category}</span></td>
            <td>${formatCurrency(p.price)}</td>
            <td><strong>${p.quantity}</strong></td>
            <td>
                <span class="${p.status === 'LOW STOCK' ? 'low' : 'stock'}">
                    ${p.status}
                </span>
            </td>
            <td>
                ${isAdmin ? `<button onclick="deleteProduct(${p.id})">Delete</button>` : `<small style="color:#94a3b8;">Read Only</small>`}
            </td>
        </tr>
    `).join("");
}

function setupInventoryFilters() {
    const searchInput = document.getElementById("searchInput");
    const categoryFilter = document.getElementById("categoryFilter");

    function applyFilter() {
        const query = (searchInput ? searchInput.value : "").toLowerCase();
        const cat = categoryFilter ? categoryFilter.value : "";

        const filtered = products.filter(p => {
            const matchesQuery = !query ||
                p.name.toLowerCase().includes(query) ||
                p.sku.toLowerCase().includes(query) ||
                p.category.toLowerCase().includes(query);
            const matchesCat = !cat || p.category === cat;
            return matchesQuery && matchesCat;
        });
        renderProductTable(filtered);
    }

    if (searchInput) searchInput.addEventListener("input", applyFilter);
    if (categoryFilter) categoryFilter.addEventListener("change", applyFilter);
}

function setupAddProductForm() {
    const form = document.getElementById("productForm");
    if (!form) return;

    form.addEventListener("submit", async function (e) {
        e.preventDefault();

        const warehouseInputs = document.querySelectorAll(".warehouse-quantity");
        const warehouseStock = Array.from(warehouseInputs).map(input => ({
            warehouse_id: Number(input.dataset.id),
            quantity: Number(input.value) || 0
        }));

        const totalQty = warehouseStock.reduce((s, i) => s + i.quantity, 0);

        const newProd = {
            name: document.getElementById("name").value.trim(),
            sku: document.getElementById("sku").value.trim(),
            category: document.getElementById("category").value,
            price: Number(document.getElementById("price").value),
            quantity: totalQty,
            reorder_level: Number(document.getElementById("reorderLevel").value),
            description: (document.getElementById("description") ? document.getElementById("description").value : "").trim(),
            warehouses: warehouseStock
        };

        try {
            await apiPost("/products", newProd);
            alert("Product added successfully!");
            form.reset();
            closeModal();
            initInventory();
        } catch (err) {
            alert("Failed to add product: " + err.message);
        }
    });
}

async function deleteProduct(id) {
    if (!confirm(`Are you sure you want to delete Product #${id}?`)) return;
    try {
        await apiDelete(`/products/${id}`);
        alert("Product deleted successfully.");
        initInventory();
    } catch (error) {
        alert("Could not delete product: " + error.message);
    }
}

function openModal() {
    const modal = document.getElementById("productModal");
    if (modal) {
        modal.classList.add("show");
        loadWarehouseInputs();
    }
}

function closeModal() {
    const modal = document.getElementById("productModal");
    if (modal) modal.classList.remove("show");
}

function loadWarehouseInputs() {
    const container = document.getElementById("warehouseInputs");
    if (!container) return;

    if (warehouses.length === 0) {
        container.innerHTML = "<p>No warehouses configured.</p>";
        return;
    }

    container.innerHTML = warehouses.map(w => `
        <div class="warehouse-input">
            <div>
                <strong>${w.name}</strong>
                <small>${w.location}</small>
            </div>
            <input type="number" min="0" value="0" class="warehouse-quantity" data-id="${w.id}">
        </div>
    `).join("");
}

// 3. WAREHOUSES
async function initWarehouses() {
    try {
        warehouses = await apiGet("/warehouses");
        products = await apiGet("/products");

        const whList = document.getElementById("warehousesList");
        if (whList) {
            whList.innerHTML = warehouses.map(w => `
                <div class="warehouse-card">
                    <div>
                        <h3>${w.name}</h3>
                        <p>${w.location}</p>
                    </div>
                    <div class="warehouse-stock">
                        <strong>${w.capacity}</strong>
                        <span>max capacity</span>
                    </div>
                    <span class="stock">ACTIVE HUB</span>
                </div>
            `).join("");
        }

        const select = document.getElementById("warehouseProductSelect");
        if (select) {
            select.innerHTML = '<option value="">Select a product to view stock distribution</option>' +
                products.map(p => `<option value="${p.id}">${p.name} (${p.sku})</option>`).join("");

            select.addEventListener("change", async function () {
                const prodId = this.value;
                const details = document.getElementById("warehouseDetails");
                if (!prodId) {
                    details.innerHTML = '<div class="empty-message">Select a product to view warehouse-wise stock.</div>';
                    return;
                }
                details.innerHTML = '<div class="warehouse-loading">Loading warehouse stock...</div>';
                try {
                    const data = await apiGet(`/products/${prodId}/warehouses`);
                    if (data.length === 0) {
                        details.innerHTML = '<div class="empty-message">No warehouse data for this product.</div>';
                        return;
                    }
                    const lowest = Math.min(...data.map(w => w.quantity));
                    details.innerHTML = data.map(w => `
                        <div class="warehouse-card">
                            <div>
                                <h3>${w.warehouse}</h3>
                                <p>${w.location}</p>
                            </div>
                            <div class="warehouse-stock">
                                <strong>${w.quantity}</strong>
                                <span>units</span>
                            </div>
                            <span class="${w.quantity === lowest ? 'lowest' : (w.status === 'LOW STOCK' ? 'low' : 'stock')}">
                                ${w.quantity === lowest ? 'LOWEST STOCK' : w.status}
                            </span>
                        </div>
                    `).join("");
                } catch (err) {
                    details.innerHTML = '<div class="empty-message">Could not load warehouse stock.</div>';
                }
            });
        }
    } catch (error) {
        console.error("Failed to load warehouses:", error);
    }
}

// 4. LOW STOCK
async function initLowStock() {
    try {
        products = await apiGet("/products");
        const list = document.getElementById("lowStockList");
        if (!list) return;

        const lowStockItems = products.filter(p => p.status === "LOW STOCK");
        if (lowStockItems.length === 0) {
            list.innerHTML = `
                <div class="empty-message" style="background: #ecfdf5; color: #065f46; border: 1px solid #10b981; border-radius: 12px; padding: 25px;">
                    <h3>All Products Well Stocked</h3>
                    <p style="margin-top: 5px;">Currently there are zero items operating below their designated reorder thresholds.</p>
                </div>
            `;
            return;
        }

        list.innerHTML = lowStockItems.map(p => `
            <div class="low-stock-item" style="display: flex; justify-content: space-between; align-items: center; padding: 18px; background: white; border-radius: 10px; margin-bottom: 12px; border-left: 5px solid #ef4444; box-shadow: 0 2px 4px rgba(0,0,0,0.04);">
                <div>
                    <h3 style="font-size: 16px;">${p.name}</h3>
                    <small style="color: #64748b;">SKU: ${p.sku} | Category: ${p.category} | Price: ${formatCurrency(p.price)}</small>
                    <p style="margin-top: 5px; font-size: 13px; color: #b91c1c;">
                        Deficit: Restock at least <strong>${Math.max(p.reorder_level - p.quantity, 1)}</strong> units to reach safety threshold.
                    </p>
                </div>
                <div style="text-align: right;">
                    <span style="font-size: 18px; font-weight: bold; color: #ef4444;">
                        ${p.quantity} / ${p.reorder_level} units
                    </span>
                </div>
            </div>
        `).join("");
    } catch (e) {
        console.error("Failed to load low stock:", e);
    }
}

// 5. STOCK IN (Admin Only)
async function initStockIn() {
    if (currentUser && currentUser.role !== "admin") {
        alert("Access Restricted: Stock In operation is available for Administrators only.");
        window.location.href = "index.html";
        return;
    }

    const productSelect = document.getElementById("stockProduct");
    const warehouseSelect = document.getElementById("stockWarehouse");
    const form = document.getElementById("stockInForm");
    const message = document.getElementById("stockMessage");

    if (!productSelect || !warehouseSelect || !form) return;

    try {
        const productData = await apiGet("/products");
        productSelect.innerHTML = '<option value="">Select Product</option>' +
            productData.map(p => `<option value="${p.id}">${p.name} (${p.sku})</option>`).join("");
    } catch (error) {
        if (message) message.innerHTML = `<div class="alert-box show error">Could not load products.</div>`;
    }

    try {
        const warehouseData = await apiGet("/warehouses");
        warehouseSelect.innerHTML = '<option value="">Select Warehouse</option>' +
            warehouseData.map(w => `<option value="${w.id}">${w.name}</option>`).join("");
    } catch (error) {
        if (message) message.innerHTML = `<div class="alert-box show error">Could not load warehouses.</div>`;
    }

    form.addEventListener("submit", async function (event) {
        event.preventDefault();
        const productId = Number(productSelect.value);
        const warehouseId = Number(warehouseSelect.value);
        const quantity = Number(document.getElementById("stockQuantity").value);
        const reference = document.getElementById("stockReference").value.trim();

        if (!productId || !warehouseId || !quantity || quantity <= 0) {
            if (message) message.innerHTML = `<div class="alert-box show error">Please fill all fields accurately.</div>`;
            return;
        }

        try {
            const result = await apiPost("/stock-in", {
                product_id: productId,
                warehouse_id: warehouseId,
                quantity: quantity,
                reference_note: reference
            });

            if (message) message.innerHTML = `
                <div class="alert-box show success">
                    <strong>Stock received successfully!</strong><br>
                    ${result.message || "Inventory updated in database."}
                </div>
            `;
            form.reset();
        } catch (error) {
            if (message) message.innerHTML = `
                <div class="alert-box show error">
                    <strong>Stock In failed.</strong><br>${error.message}
                </div>
            `;
        }
    });
}

// 6. STOCK OUT (Admin Only)
async function initStockOut() {
    if (currentUser && currentUser.role !== "admin") {
        alert("Access Restricted: Stock Out operation is available for Administrators only.");
        window.location.href = "index.html";
        return;
    }

    const productSelect = document.getElementById("outProduct");
    const warehouseSelect = document.getElementById("outWarehouse");
    const form = document.getElementById("stockOutForm");
    const message = document.getElementById("stockOutMessage");

    if (!productSelect || !warehouseSelect || !form) return;

    try {
        const productData = await apiGet("/products");
        productSelect.innerHTML = '<option value="">Select Product</option>' +
            productData.map(p => `<option value="${p.id}">${p.name} (${p.sku})</option>`).join("");
    } catch (error) {
        if (message) message.innerHTML = `<div class="alert-box show error">Could not load products.</div>`;
    }

    try {
        const warehouseData = await apiGet("/warehouses");
        warehouseSelect.innerHTML = '<option value="">Select Warehouse</option>' +
            warehouseData.map(w => `<option value="${w.id}">${w.name}</option>`).join("");
    } catch (error) {
        if (message) message.innerHTML = `<div class="alert-box show error">Could not load warehouses.</div>`;
    }

    form.addEventListener("submit", async function (event) {
        event.preventDefault();
        const productId = Number(productSelect.value);
        const warehouseId = Number(warehouseSelect.value);
        const quantity = Number(document.getElementById("outQuantity").value);
        const reference = document.getElementById("outReference").value.trim();

        if (!productId || !warehouseId || !quantity || quantity <= 0) {
            if (message) message.innerHTML = `<div class="alert-box show error">Please enter valid values.</div>`;
            return;
        }

        try {
            const result = await apiPost("/stock-out", {
                product_id: productId,
                warehouse_id: warehouseId,
                quantity: quantity,
                reference_note: reference
            });

            if (message) message.innerHTML = `
                <div class="alert-box show success">
                    <strong>Stock issued successfully!</strong><br>
                    ${result.message || "Inventory updated."}
                </div>
            `;
            form.reset();
        } catch (error) {
            if (message) message.innerHTML = `
                <div class="alert-box show error">
                    <strong>Stock Out failed.</strong><br>${error.message}
                </div>
            `;
        }
    });
}

// 7. ORDERS & STOCK REQUESTS (User creates, Admin reviews & approves)
async function initOrders() {
    const productSelect = document.getElementById("orderProduct");
    const warehouseSelect = document.getElementById("orderWarehouse");
    const form = document.getElementById("orderForm");
    const message = document.getElementById("orderMessage");

    if (productSelect && warehouseSelect) {
        try {
            products = await apiGet("/products");
            productSelect.innerHTML = '<option value="">Select Product</option>' +
                products.map(p => `<option value="${p.id}">${p.name} (${p.sku})</option>`).join("");
            warehouses = await apiGet("/warehouses");
            warehouseSelect.innerHTML = '<option value="">Select Warehouse</option>' +
                warehouses.map(w => `<option value="${w.id}">${w.name}</option>`).join("");
        } catch (e) {
            console.error("Failed to load options for orders:", e);
        }
    }

    if (form) {
        form.addEventListener("submit", async function(e) {
            e.preventDefault();
            const productId = Number(productSelect.value);
            const warehouseId = Number(warehouseSelect.value);
            const quantity = Number(document.getElementById("orderQuantity").value);

            try {
                await apiPost("/orders", {
                    user_id: currentUser ? currentUser.id : 1,
                    user_name: currentUser ? currentUser.name : "Staff User",
                    product_id: productId,
                    warehouse_id: warehouseId,
                    quantity: quantity
                });
                if (message) message.innerHTML = `<div class="alert-box show success">Stock request submitted! Admin has received your request for approval.</div>`;
                form.reset();
                loadOrdersTable();
            } catch (err) {
                if (message) message.innerHTML = `<div class="alert-box show error">Failed to submit request: ${err.message}</div>`;
            }
        });
    }

    loadOrdersTable();
}

async function loadOrdersTable() {
    const table = document.getElementById("ordersTable");
    if (!table) return;

    try {
        const orders = await apiGet("/orders");
        if (orders.length === 0) {
            table.innerHTML = '<tr><td colspan="8" class="loading">No stock requests found.</td></tr>';
            return;
        }

        const isAdmin = currentUser && currentUser.role === "admin";

        table.innerHTML = orders.map(o => `
            <tr>
                <td>#${o.id}</td>
                <td><strong>${o.user_name}</strong></td>
                <td>${o.product_name}</td>
                <td>${o.warehouse_name}</td>
                <td><strong>${o.quantity} units</strong></td>
                <td>${new Date(o.request_date).toLocaleDateString()}</td>
                <td>
                    <span class="status-pill status-${o.status.toLowerCase()}">${o.status}</span>
                </td>
                <td>
                    ${isAdmin && o.status === 'PENDING' ? `
                        <button class="btn-approve" onclick="updateOrderStatus(${o.id}, 'APPROVED')">Approve</button>
                        <button class="btn-reject" onclick="updateOrderStatus(${o.id}, 'REJECTED')">Reject</button>
                    ` : `<span style="font-size:12px; color:#64748b; font-weight:600;">${o.status}</span>`}
                </td>
            </tr>
        `).join("");

    } catch (err) {
        table.innerHTML = `<tr><td colspan="8" class="loading">Could not load orders: ${err.message}</td></tr>`;
    }
}

async function updateOrderStatus(orderId, status) {
    if (!confirm(`Are you sure you want to mark Order #${orderId} as ${status}?`)) return;
    try {
        await apiPut(`/orders/${orderId}/status`, { status });
        alert(`Order #${orderId} ${status} successfully! Stock balances updated.`);
        loadOrdersTable();
    } catch (err) {
        alert(`Failed to update order: ${err.message}`);
    }
}

// 8. USER MANAGEMENT (Admin Only)
async function initUsers() {
    if (currentUser && currentUser.role !== "admin") {
        alert("Access Restricted: User Administration is available for Administrators only.");
        window.location.href = "index.html";
        return;
    }

    const form = document.getElementById("addUserForm");
    const msg = document.getElementById("userFormMessage");

    if (form) {
        form.addEventListener("submit", async function(e) {
            e.preventDefault();
            const name = document.getElementById("newUserName").value.trim();
            const email = document.getElementById("newUserEmail").value.trim();
            const password = document.getElementById("newUserPassword").value.trim();
            const role = document.getElementById("newUserRole").value;

            try {
                await apiPost("/users", { name, email, password, role });
                if (msg) msg.innerHTML = `<div class="alert-box show success">User account ${email} created successfully!</div>`;
                form.reset();
                loadUsersTable();
            } catch (err) {
                if (msg) msg.innerHTML = `<div class="alert-box show error">Failed to create user: ${err.message}</div>`;
            }
        });
    }

    loadUsersTable();
}

async function loadUsersTable() {
    const table = document.getElementById("usersTable");
    if (!table) return;

    try {
        const users = await apiGet("/users");
        table.innerHTML = users.map(u => `
            <tr>
                <td>#${u.id}</td>
                <td><strong>${u.name}</strong></td>
                <td>${u.email}</td>
                <td><span class="badge ${u.role === 'admin' ? 'primary' : 'success'}">${u.role.toUpperCase()}</span></td>
                <td>${new Date(u.created_at).toLocaleDateString()}</td>
                <td>
                    ${u.email !== 'admin@warehouse.com' ? `<button onclick="deleteUserAccount(${u.id})">Delete</button>` : `<small style="color:#64748b;">Primary Admin</small>`}
                </td>
            </tr>
        `).join("");
    } catch (err) {
        table.innerHTML = `<tr><td colspan="6" class="loading">Could not load users: ${err.message}</td></tr>`;
    }
}

async function deleteUserAccount(userId) {
    if (!confirm(`Are you sure you want to delete user account #${userId}?`)) return;
    try {
        await apiDelete(`/users/${userId}`);
        alert("User deleted successfully.");
        loadUsersTable();
    } catch (err) {
        alert("Failed to delete user: " + err.message);
    }
}

// ROUTER
document.addEventListener("DOMContentLoaded", () => {
    checkAuth();

    const path = window.location.pathname.toLowerCase();

    if (path.endsWith("inventory.html")) {
        initInventory();
    } else if (path.endsWith("warehouses.html")) {
        initWarehouses();
    } else if (path.endsWith("stock-in.html")) {
        initStockIn();
    } else if (path.endsWith("stock-out.html")) {
        initStockOut();
    } else if (path.endsWith("low-stock.html")) {
        initLowStock();
    } else if (path.endsWith("orders.html")) {
        initOrders();
    } else if (path.endsWith("users.html")) {
        initUsers();
    } else if (path.endsWith("login.html")) {
        // Login page specific script handles form submission
    } else {
        initDashboard();
    }
});