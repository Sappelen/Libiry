[app]

# Title of your application
title = Libiry

# Package name
package.name = libiry

# Package domain (needed for android/ios packaging)
package.domain = org.libiry

# Source code where the main.py lives
source.dir = .

# Source files to include
source.include_exts = py,png,jpg,jpeg,ico,json

# Application versioning
version = 1.0.0

# Application requirements
requirements = python3,kivy,pillow,sqlite3

# Supported orientations (portrait, landscape, all)
orientation = all

# Android specific
fullscreen = 0

# Android permissions
android.permissions = READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE

# Android API
android.api = 33
android.minapi = 21
android.ndk = 25b

# iOS specific
ios.kivy_ios_url = https://github.com/kivy/kivy-ios
ios.kivy_ios_branch = master

# OSX specific
osx.python_version = 3
osx.kivy_version = 2.3.0

[buildozer]

# Log level (0 = error, 1 = info, 2 = debug)
log_level = 2

# Warn on root
warn_on_root = 1
