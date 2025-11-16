-- Charge Point table - Main table for charging point information
CREATE TABLE cp (
    id TEXT PRIMARY KEY,                    -- Charger identifier (from OCPP messages)
    name TEXT NOT NULL DEFAULT '',         -- Human-readable name
    vendor TEXT NOT NULL DEFAULT '',       -- Charger vendor (from BootNotification)
    model TEXT NOT NULL DEFAULT '',        -- Charger model (from BootNotification)
    serial_number TEXT DEFAULT '',         -- Serial number (from BootNotification)
    firmware_version TEXT DEFAULT '',      -- Firmware version (from BootNotification)
    iccid TEXT DEFAULT '',                 -- SIM card ICCID (optional)
    imsi TEXT DEFAULT '',                  -- SIM card IMSI (optional)
    status TEXT DEFAULT 'Unknown',         -- Current charger status
    is_connected INTEGER NOT NULL DEFAULT 0, -- Connection status (1=connected, 0=disconnected)
    -- Timestamp fields for activity tracking
    last_heartbeat_at DATETIME,            -- Last heartbeat received
    last_boot_at DATETIME,                 -- Last boot notification
    last_connect_at DATETIME,              -- Last WebSocket connection
    last_tx_start_at DATETIME,             -- Last transaction start
    last_tx_stop_at DATETIME,              -- Last transaction stop
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Charge Point Connectors - Individual connectors per charge point
CREATE TABLE cp_conn (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cp_id TEXT NOT NULL,              -- Reference to charger
    conn_id INTEGER NOT NULL,         -- Connector number (1, 2, etc.)
    status TEXT NOT NULL DEFAULT 'Available', -- Connector status
    error_code TEXT DEFAULT '',            -- Current error code if any
    vendor_error_code TEXT DEFAULT '',     -- Vendor-specific error code
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (cp_id) REFERENCES cp(id) ON DELETE CASCADE,
    UNIQUE(cp_id, conn_id)       -- Ensure unique connector per charger
);

-- Transaction table - Individual charging sessions
CREATE TABLE tx (
    id INTEGER PRIMARY KEY AUTOINCREMENT,  -- Auto-generated transaction ID
    tx_id INTEGER UNIQUE,         -- OCPP transaction ID (unique across system)
    cp_id TEXT NOT NULL,              -- Charger where transaction occurred
    cp_conn_id INTEGER NOT NULL,     -- Connector used for transaction
    id_tag TEXT NOT NULL,                  -- User identification tag
    start_time DATETIME NOT NULL,          -- Transaction start timestamp
    stop_time DATETIME,                    -- Transaction stop timestamp (NULL for active)
    meter_start INTEGER DEFAULT 0,         -- Starting meter value (Wh)
    meter_stop INTEGER,                    -- Ending meter value (Wh)
    energy_delivered INTEGER DEFAULT 0,    -- Total energy delivered (Wh)
    stop_reason TEXT DEFAULT '',           -- Reason for stopping transaction
    status TEXT NOT NULL DEFAULT 'Active', -- Transaction status (Active, Completed, Aborted)
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (cp_id) REFERENCES cp(id) ON DELETE CASCADE,
    FOREIGN KEY (cp_conn_id) REFERENCES cp_conn(id) ON DELETE CASCADE
);

-- Meter Values table - Time-series data for energy consumption
CREATE TABLE meter_val (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tx_id INTEGER,               -- Link to transaction (NULL for non-transaction values)
    cp_id TEXT NOT NULL,             -- Charger that sent the value
    cp_conn_id INTEGER NOT NULL,    -- Connector number
    timestamp DATETIME NOT NULL,          -- When the reading was taken
    measurand TEXT NOT NULL,              -- What was measured (Energy.Active.Import.Register, etc.)
    value REAL NOT NULL,                  -- The measured value
    unit TEXT NOT NULL DEFAULT 'Wh',     -- Unit of measurement
    context TEXT NOT NULL DEFAULT 'Sample.Periodic', -- Context (Sample.Periodic, Transaction.Begin, etc.)
    location TEXT NOT NULL DEFAULT 'Outlet', -- Location (Outlet, Cable, EV, etc.)
    phase TEXT DEFAULT '',               -- Phase information (L1, L2, L3, etc.)
    format TEXT NOT NULL DEFAULT 'Raw',  -- Format (Raw, SignedData)
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tx_id) REFERENCES tx(id) ON DELETE CASCADE,
    FOREIGN KEY (cp_id) REFERENCES cp(id) ON DELETE CASCADE,
    FOREIGN KEY (cp_conn_id) REFERENCES cp_conn(id) ON DELETE CASCADE
);

-- Charger Errors table - Error events from chargers
CREATE TABLE cp_err (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cp_id TEXT NOT NULL,             -- Charger reporting the error
    cp_conn_id INTEGER,              -- Connector with error (NULL for charger-level errors)
    error_code TEXT NOT NULL,             -- Standard OCPP error code
    vendor_error_code TEXT DEFAULT '',    -- Vendor-specific error code
    error_description TEXT DEFAULT '',    -- Human-readable error description
    vendor_error_info TEXT DEFAULT '',    -- Additional vendor error information
    timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at DATETIME,                 -- When error was resolved (NULL if still active)
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (cp_id) REFERENCES cp(id) ON DELETE CASCADE,
    FOREIGN KEY (cp_conn_id) REFERENCES cp_conn(id) ON DELETE CASCADE
);

-- Indexes for performance optimization
CREATE INDEX idx_chargers_status ON cp(status);
CREATE INDEX idx_chargers_connected ON cp(is_connected);
CREATE INDEX idx_chargers_last_heartbeat ON cp(last_heartbeat_at);

CREATE INDEX idx_connector_charger_id ON cp_conn(cp_id);
CREATE INDEX idx_connector_status ON cp_conn(status);

CREATE INDEX idx_transactions_charger_id ON tx(cp_id);
CREATE INDEX idx_transactions_connector_id ON tx(cp_conn_id);
CREATE INDEX idx_transactions_id_tag ON tx(id_tag);
CREATE INDEX idx_transactions_status ON tx(status);
CREATE INDEX idx_transactions_start_time ON tx(start_time);
CREATE INDEX idx_transactions_transaction_id ON tx(tx_id);

CREATE INDEX idx_meter_values_transaction_id ON meter_val(tx_id);
CREATE INDEX idx_meter_values_charger_id ON meter_val(cp_id);
CREATE INDEX idx_meter_values_connector_id ON meter_val(cp_conn_id);
CREATE INDEX idx_meter_values_timestamp ON meter_val(timestamp);
CREATE INDEX idx_meter_values_measurand ON meter_val(measurand);

CREATE INDEX idx_charger_errors_charger_id ON cp_err(cp_id);
CREATE INDEX idx_charger_errors_connector_id ON cp_err(cp_conn_id);
CREATE INDEX idx_charger_errors_timestamp ON cp_err(timestamp);
CREATE INDEX idx_charger_errors_resolved ON cp_err(resolved_at);