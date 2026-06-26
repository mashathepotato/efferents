# Landing screenshots

`dashboard.png` is a real screenshot of the demo dashboard — not a mockup.

To regenerate after the demo output or dashboard template changes:

```bash
efferents demo smoke-lab                       # writes ./efferents-demo/
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
"$CHROME" --headless=new --hide-scrollbars --force-device-scale-factor=2 \
  --window-size=860,1080 \
  --screenshot=web/landing/img/dashboard.png \
  "file://$(pwd)/efferents-demo/dashboard.html"
```
