[app]
title = Aprendix
package.name = aprendix
package.domain = io.aprendix
source.dir = ..
source.include_exts = py,html,js,txt,json,db,png,jpg,jpeg,webp,kv
source.include_patterns = src/aprendix/**,mobile/aprendix_mobile/**,mobile/assets/**,main.py,LICENSE
source.exclude_dirs = tests,.git,.pytest_cache,.venv-aprendix-desktop,build,dist,__pycache__,scripts,packaging
source.exclude_patterns = aprendix-phase*.png,BASELINE*.json,SEARCH-BENCHMARK*.json,DEPENDENCY-AUDIT*.json,SBOM*.json,*.log,*.pdf
version = 1.0.0
requirements = python3==3.11.14,hostpython3==3.11.14,kivy==2.3.1,pyjnius
orientation = portrait
fullscreen = 0
presplash.color = #060911
android.api = 35
android.minapi = 26
android.ndk = 28c
android.archs = arm64-v8a
android.accept_sdk_license = True
android.permissions = POST_NOTIFICATIONS,VIBRATE
android.add_src = mobile/android/src
android.gradle_dependencies = androidx.core:core:1.13.1,com.google.mlkit:text-recognition:16.0.1,org.jetbrains.kotlin:kotlin-stdlib:1.8.22,org.jetbrains.kotlin:kotlin-stdlib-jdk7:1.8.22,org.jetbrains.kotlin:kotlin-stdlib-jdk8:1.8.22
android.enable_androidx = True
android.release_artifact = apk
p4a.branch = v2026.05.09
p4a.hook = mobile/android/p4a_hook.py
p4a.local_recipes = mobile/android/recipes
p4a.extra_args = --require-perfect-match --allow-replace-dist

[buildozer]
log_level = 2
warn_on_root = 1
