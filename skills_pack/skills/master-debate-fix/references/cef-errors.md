## CEF Filesystem Errors

**Symptom:** "filesystem error: The specified mount cannot be handled by any of the filesystem adapters"

**Cause:** Linux-wallpaperengine CEF component incompatible with snap-mounted Steam folders

**Workarounds:**
1. Use `--silent` flag to reduce CEF output
2. Web wallpapers may fail due to CEF sandbox restrictions  
3. Consider running Steam Wallpaper Engine directly instead of linux-wallpaperengine for web/video types
4. Some systems require CEF sandbox disabled: may need custom build flag

**Error Pattern:**
```
filesystem error: The specified mount cannot be handled by any of the filesystem adapters: Success [path/to/wallpaper]
```

This occurs when CEF tries to access files through the snap mount namespace.