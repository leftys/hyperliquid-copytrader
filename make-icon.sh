#!/bin/bash

# Create necessary directories
mkdir -p icon.iconset

# Convert SVG to PNG at different sizes using magick
magick convert icon.svg -resize 16x16 icon.iconset/icon_16x16.png
magick convert icon.svg -resize 32x32 icon.iconset/icon_16x16@2x.png
magick convert icon.svg -resize 32x32 icon.iconset/icon_32x32.png
magick convert icon.svg -resize 64x64 icon.iconset/icon_32x32@2x.png
magick convert icon.svg -resize 128x128 icon.iconset/icon_128x128.png
magick convert icon.svg -resize 256x256 icon.iconset/icon_128x128@2x.png
magick convert icon.svg -resize 256x256 icon.iconset/icon_256x256.png
magick convert icon.svg -resize 512x512 icon.iconset/icon_256x256@2x.png
magick convert icon.svg -resize 512x512 icon.iconset/icon_512x512.png
magick convert icon.svg -resize 1024x1024 icon.iconset/icon_512x512@2x.png

# Convert to icns
iconutil -c icns icon.iconset

# Clean up
rm -R icon.iconset