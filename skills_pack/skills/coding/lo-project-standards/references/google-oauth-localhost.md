# Google OAuth localhost Access

## Problem
Google OAuth `origin_mismatch` error when origin is `http://localhost:8000` even when configured in Google Cloud Console.

## Root Cause
Google's JavaScript SDK caches the origin check for 5-60 minutes. Changes to authorized origins in Google Cloud Console do not take immediate effect.

## Solution
Always add **both variants** of localhost origin:
```
Authorized JavaScript origins:
  - http://localhost:8000
  - https://localhost:8000

Authorized redirect URIs:
  - http://localhost:8000/login
  - https://localhost:8000/login
```

After adding, wait 5-60 minutes OR use a hard-refresh (Ctrl+F5) in an incognito window.

## Dev Mode Fallback
When Google OAuth is blocked, provide a direct login button that sets localStorage:

```javascript
// In login.html script
const localBtn = document.getElementById('btn-local-login');
if (localBtn) {
  localBtn.addEventListener('click', function() {
    localStorage.setItem('mc_auth', '{"sub":"USER_ID","name":"NAME","email":"EMAIL"}');
    localStorage.setItem('mc_token', 'bypass');
    window.location.href = redirect || '/admin';
  });
}
```

On the server, check for bypass token:
```python
# In /api/user or /api/user/settings endpoint
if token == "bypass":
    user_id = "YOUR_USER_ID"
else:
    user_id = _get_user_id_from_token(token)
```

Remove the dev button before production - it's only for localhost testing while OAuth propagates.