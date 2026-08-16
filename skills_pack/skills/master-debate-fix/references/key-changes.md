## Key Files Modified for Master Debate Stability

### core/engine.py
- Lines 713-714: Reduced TIMEOUT and CONNECT_TIMEOUT
- Line 993-996: Added early return for missing API keys
- Line 1089: Fixed 429 retry condition

### tools/debate.py  
- Line 128: Added auto_poll=False to Engine init
- Lines 28-29: Reduced ROUND_TIMEOUT and MAX_CONCURRENT
- Lines 53, 78: Restricted to fast providers only

### core/health_poller.py
- Lines 167-97: Updated _PING_ENDPOINTS config format
- Lines 100-126: Added API key checks before pinging providers