# ENI Swarm Pattern — Frontend Form Wiring

When adding new form fields to admin/index.html:

## JavaScript Form Handler Pattern
```javascript
form.addEventListener('submit', function (e) {
  e.preventDefault();
  const settings = {
    field_name: $('#field-id') ? $('#field-id').value : '',
  };
  // Multi-tenant save
  fetch('/api/user/settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token: authToken, settings: settings }),
  });
});
```

## Settings Loading Pattern  
```javascript
function loadUserSettings() {
  fetch('/api/user/settings?token=' + encodeURIComponent(authToken))
    .then(function (r) { return r.json(); })
    .then(function (data) {
      if (data.ok && data.settings) {
        setVal('#field-id', data.settings.field_name);
      }
    });
}
```

## Backend Mapping (.env)
Map form field to env var in `_save_settings()`:
```python
mapping = {
  "field_name": "MASTERCHIEF_FIELD_NAME",
}
```

Map env var back to form field in `_env_to_settings_key()`:
```python
"MASTERCHIEF_FIELD_NAME": "field_name",
```