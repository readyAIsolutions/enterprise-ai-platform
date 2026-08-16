# Environment Variable Persistence Pattern

## Pattern Overview
When implementing admin settings forms, persistence to environment variables follows a three-tier approach:

1. **Frontend Storage**: localStorage/sessionStorage for immediate UI feedback
2. **Backend Persistence**: Writing to .env files for server configuration
3. **Runtime Updates**: Live Config class updates for runtime changes

## Implementation Example

### Frontend JavaScript
```javascript
// Save settings via API
async function saveSettings(settings) {
    try {
        const response = await fetch('/api/settings', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(settings)
        });
        
        if (response.ok) {
            // Update localStorage as fallback
            Object.entries(settings).forEach(([key, value]) => {
                localStorage.setItem(key, value);
            });
            
            showToast('Settings saved successfully!', 'success');
        }
    } catch (error) {
        showToast('Error saving settings: ' + error.message, 'error');
    }
}
```

### Backend Python (Flask)
```python
import os
from flask import Flask, request, jsonify

app = Flask(__name__)
settings_store = {}

def save_to_env(data):
    """Save settings to .env file"""
    env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    
    # Read existing .env file
    env_vars = {}
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                if '=' in line and not line.strip().startswith('#'):
                    key, value = line.strip().split('=', 1)
                    env_vars[key] = value
    
    # Update with new values
    env_vars.update(data)
    
    # Write back to .env file
    with open(env_path, 'w') as f:
        for key, value in env_vars.items():
            # Handle string values that might contain special characters
            if isinstance(value, str) and (' ' in value or '=' in value or '#' in value):
                f.write(f"{key}=\"{value}\"\n")
            else:
                f.write(f"{key}={value}\n")

@app.route('/api/settings', methods=['POST'])
def save_settings():
    """Save settings to the store and .env file"""
    try:
        data = request.get_json()
        
        # Update in-memory store
        settings_store.update(data)
        
        # Update Config class (if it exists)
        try:
            from config import Config
            Config.update_config(**data)
        except ImportError:
            pass
        
        # Save to .env file
        save_to_env(data)
        
        return jsonify({"status": "success", "message": "Settings saved successfully"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
```

### Configuration Class
```python
import os

class Config:
    """Configuration class with environment variable support"""
    
    # Service configurations
    FONOSTER_API_ENDPOINT: str = os.getenv("FONOSTER_API_ENDPOINT", "http://localhost:8080")
    USESEND_SMTP_HOST: str = os.getenv("USESEND_SMTP_HOST", "localhost")
    ODOO19_HOST: str = os.getenv("ODOO19_HOST", "localhost")
    
    @classmethod
    def update_config(cls, **kwargs):
        """
        Update configuration values from a dictionary
        This method is used to persist settings from the admin forms
        """
        for key, value in kwargs.items():
            if hasattr(cls, key):
                setattr(cls, key, value)
                # Also set in environment for subprocesses
                os.environ[key] = str(value)
    
    @classmethod
    def to_dict(cls):
        """Convert configuration to dictionary for serialization"""
        return {
            "FONOSTER_API_ENDPOINT": cls.FONOSTER_API_ENDPOINT,
            "USESEND_SMTP_HOST": cls.USESEND_SMTP_HOST,
            "ODOO19_HOST": cls.ODOO19_HOST,
            # ... other settings
        }
```

## Key Benefits
- **Immediate UI Updates**: localStorage provides instant feedback
- **Persistent Configuration**: .env files survive server restarts
- **Runtime Flexibility**: Config class updates allow runtime changes
- **Environment Variable Support**: Standard approach for containerized deployments

## Testing Considerations
- Mock file system operations in unit tests
- Test special character handling in environment variables
- Verify Config class updates propagate correctly
- Ensure error handling for file I/O operations