#!/bin/bash
##
## Sprint 5 Demo - Full Production Mode
## Run with MongoDB, auto-reload, and all features enabled
##

echo ">> Starting Anonymous Studio - Sprint 5 Demo Mode"
echo ""

# GUI Settings - Auto-reload for live changes
export ANON_GUI_USE_RELOADER=1
export ANON_GUI_DEBUG=1

# Development mode (enables demo role switcher)
export ANON_MODE=development

# Optional: Set hash salt (for production, use a secret value)
# export ANON_HASH_SALT=your-secret-salt-here

echo "=================================================="
echo "  Select Storage Backend"
echo "=================================================="
echo ""
echo "1) Memory    - Fast, no persistence (resets on restart)"
echo "2) DuckDB    - Local file-based, persistent, good for demo"
echo "3) MongoDB   - Production-ready, requires MongoDB running"
echo ""
read -p "Choose backend (1-3): " -n 1 -r
echo ""
echo ""

case $REPLY in
    1)
        # Memory backend
        export ANON_STORE_BACKEND=memory
        export ANON_RAW_INPUT_BACKEND=memory
        
        echo "[OK] Environment configured:"
        echo "   - Auto-reload: ENABLED"
        echo "   - Debug mode: ENABLED"
        echo "   - Store backend: Memory (in-memory)"
        echo "   - DataNode backend: Memory (in-memory)"
        echo "   - Mode: Development (demo role switcher enabled)"
        echo ""
        echo "[!] Note: All data will be lost when you stop the app"
        ;;
    2)
        # DuckDB backend
        export ANON_STORE_BACKEND=duckdb
        export ANON_RAW_INPUT_BACKEND=pickle
        
        echo "[OK] Environment configured:"
        echo "   - Auto-reload: ENABLED"
        echo "   - Debug mode: ENABLED"
        echo "   - Store backend: DuckDB (anon_studio.db)"
        echo "   - DataNode backend: Pickle (user_data/)"
        echo "   - Mode: Development (demo role switcher enabled)"
        echo ""
        echo "[*] Data persists in: anon_studio.db and user_data/"
        ;;
    3)
        # MongoDB backend
        export ANON_STORE_BACKEND=mongo
        export MONGODB_URI=mongodb://localhost:27017/anon_studio
        export ANON_RAW_INPUT_BACKEND=mongo
        export ANON_MONGO_URI=mongodb://localhost:27017/anon_studio
        export ANON_MONGO_WRITE_BATCH=5000
        
        echo "[OK] Environment configured:"
        echo "   - Auto-reload: ENABLED"
        echo "   - Debug mode: ENABLED"
        echo "   - Store backend: MongoDB"
        echo "   - DataNode backend: MongoDB"
        echo "   - Mode: Development (demo role switcher enabled)"
        echo ""
        
        # Check if MongoDB is running
        echo "[*] Checking MongoDB connection..."
        if mongosh --eval "db.adminCommand('ping')" --quiet > /dev/null 2>&1; then
            echo "[OK] MongoDB is running"
        else
            echo "[!] MongoDB is not running"
            echo ""
            read -p "Start MongoDB now? (y/n) " -n 1 -r
            echo
            echo ""
            
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                echo "[*] Attempting to start MongoDB..."
                
                # Try Docker first (most portable)
                if command -v docker &> /dev/null; then
                    # Check if mongo container already exists
                    if docker ps -a --format '{{.Names}}' | grep -q '^mongo$'; then
                        echo "[*] Starting existing mongo container..."
                        docker start mongo
                    else
                        echo "[*] Creating new mongo container..."
                        docker run -d -p 27017:27017 --name mongo mongo:latest
                    fi
                    
                    # Wait for MongoDB to be ready
                    echo "[*] Waiting for MongoDB to be ready..."
                    for i in {1..10}; do
                        if mongosh --eval "db.adminCommand('ping')" --quiet > /dev/null 2>&1; then
                            echo "[OK] MongoDB is now running"
                            break
                        fi
                        sleep 1
                    done
                    
                # Try systemd (Linux)
                elif command -v systemctl &> /dev/null; then
                    echo "[*] Starting MongoDB via systemd..."
                    sudo systemctl start mongod
                    sleep 2
                    if mongosh --eval "db.adminCommand('ping')" --quiet > /dev/null 2>&1; then
                        echo "[OK] MongoDB is now running"
                    else
                        echo "[!] Failed to start MongoDB via systemd"
                        exit 1
                    fi
                    
                # Try Homebrew (macOS)
                elif command -v brew &> /dev/null; then
                    echo "[*] Starting MongoDB via Homebrew..."
                    brew services start mongodb-community
                    sleep 2
                    if mongosh --eval "db.adminCommand('ping')" --quiet > /dev/null 2>&1; then
                        echo "[OK] MongoDB is now running"
                    else
                        echo "[!] Failed to start MongoDB via Homebrew"
                        exit 1
                    fi
                    
                else
                    echo "[X] Could not find docker, systemctl, or brew to start MongoDB"
                    echo "    Please start MongoDB manually and run this script again"
                    exit 1
                fi
            else
                echo "[X] Cannot continue without MongoDB. Exiting."
                exit 1
            fi
        fi
        ;;
    *)
        echo "[X] Invalid selection. Exiting."
        exit 1
        ;;
esac

echo ""
echo ">> Starting Taipy application..."
echo "   Open http://localhost:5000 in your browser"
echo ""
echo "Press Ctrl+C to stop"
echo ""

# Run the app
taipy run main.py
