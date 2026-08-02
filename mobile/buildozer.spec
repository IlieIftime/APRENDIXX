[app]
title = Aprendix
package.name = aprendix
package.domain = io.aprendix
source.dir = ..
source.include_exts = py,html,js,txt,json,db,png,jpg,kv
source.include_patterns = src/aprendix/**,mobile/aprendix_mobile/**,mobile/assets/**,main.py,LICENSE
source.exclude_dirs = tests,.git,.pytest_cache,.venv-aprendix-desktop,build,dist,__pycache__
version = 0.18.0
requirements = python3,kivy==2.3.0,cryptography,pyjnius
orientation = portrait
fullscreen = 0
presplash.color = #060911
android.api = 34
android.minapi = 26
android.ndk = 25b
android.archs = arm64-v8a
android.accept_sdk_license = True
android.permissions = POST_NOTIFICATIONS,VIBRATE
android.add_src = mobile/android/src
android.gradle_dependencies = androidx.core:core:1.13.1
android.enable_androidx = True
p4a.branch = v2024.01.21
p4a.hook = mobile/android/p4a_hook.py

[buildozer]
log_level = 2
warn_on_root = 1
