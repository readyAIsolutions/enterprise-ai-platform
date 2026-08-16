# Channel Mutual Exclusion UI Pattern

When multiple checkboxes should act as radio-button-like mutual exclusion:

## HTML Structure
```html
<input type="checkbox" name="channel" value="email"> Email
<input type="checkbox" name="channel" value="voice"> Voice  
<input type="checkbox" name="channel" value="both"> Both
```

## JavaScript Implementation
```javascript
function initChannelExclusion() {
    const emailCb = document.querySelector('input[name="channel"][value="email"]');
    const voiceCb = document.querySelector('input[name="channel"][value="voice"]');
    const bothCb = document.querySelector('input[name="channel"][value="both"]');
    if (!emailCb || !voiceCb || !bothCb) return;
    bothCb.addEventListener('change', function() {
        if (this.checked) { emailCb.checked = false; voiceCb.checked = false; }
    });
    emailCb.addEventListener('change', function() { if (this.checked) bothCb.checked = false; });
    voiceCb.addEventListener('change', function() { if (this.checked) bothCb.checked = false; });
}
```

## Key Points
- Call `initChannelExclusion()` in your main `init()` function
- Use `querySelector` with attribute selectors for precise targeting
- Always guard against null elements (field might not exist in some tabs)
- Preserve "Both" as the primary exclusivity trigger - it deselects both others
- Each individual checkbox deselects "Both" when chosen