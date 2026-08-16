# Channel Selection Mutual Exclusion Pattern

## HTML (Admin Settings Form)
```html
<div class="form-group">
  <label>Channels</label>
  <div style="display:flex; gap:16px; margin-top:8px;">
    <label style="display:flex; align-items:center; gap:6px; cursor:pointer;">
      <input type="checkbox" name="channel" value="phone" id="channel-phone">
      <span>Phone (Voice)</span>
    </label>
    <label style="display:flex; align-items:center; gap:6px; cursor:pointer;">
      <input type="checkbox" name="channel" value="email" id="channel-email">
      <span>Email</span>
    </label>
    <label style="display:flex; align-items:center; gap:6px; cursor:pointer;">
      <input type="checkbox" name="channel" value="both" id="channel-both">
      <span>Both</span>
    </label>
  </div>
</div>
```

## JavaScript (admin.js)
```javascript
function initChannelExclusion() {
  var checkboxes = document.querySelectorAll('input[name="channel"]');
  checkboxes.forEach(function (cb) {
    cb.addEventListener('change', function () {
      if (cb.value === 'both' && cb.checked) {
        // Uncheck Phone and Email when Both is checked
        document.getElementById('channel-phone').checked = false;
        document.getElementById('channel-email').checked = false;
      } else if ((cb.value === 'phone' || cb.value === 'email') && cb.checked) {
        // Uncheck Both when Phone or Email is checked
        document.getElementById('channel-both').checked = false;
      }
    });
  });
}

function init() {
  // ... other init code ...
  initChannelExclusion();
}
```

## Reading Selected Channels
```javascript
function getSelectedChannels() {
  var checked = document.querySelectorAll('input[name="channel"]:checked');
  return Array.from(checked).map(function (cb) { return cb.value; });
}
// Returns ["phone"], ["email"], ["both"], or ["phone", "email"]
```

## Server-side Handling
The `getSelectedChannels()` function returns the selected values. For campaigns:
- `"both"` → use both voice and email channels
- `"phone"` → voice only
- `"email"` → email only