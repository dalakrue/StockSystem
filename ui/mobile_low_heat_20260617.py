"""Low-render-cost CSS and refresh policy for phone/reduced-motion use."""
from __future__ import annotations

from typing import Any, Mapping

LOW_HEAT_CSS = r"""
<style>
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation: none !important;
    animation-duration: 0.001ms !important;
    animation-iteration-count: 1 !important;
    scroll-behavior: auto !important;
    transition: none !important;
  }
}
html[data-new7-phone-low-heat="true"] *,
html[data-new7-phone-low-heat="true"] *::before,
html[data-new7-phone-low-heat="true"] *::after,
body.new7-phone-low-heat *,
body.new7-phone-low-heat *::before,
body.new7-phone-low-heat *::after {
  animation: none !important;
  transition: none !important;
  filter: none !important;
  backdrop-filter: none !important;
  -webkit-backdrop-filter: none !important;
  transform: none !important;
  text-shadow: none !important;
}
body.new7-phone-low-heat [class*="glow"],
body.new7-phone-low-heat [class*="grid"],
body.new7-phone-low-heat [class*="background"]::before,
body.new7-phone-low-heat [class*="background"]::after {
  animation: none !important;
  filter: none !important;
  backdrop-filter: none !important;
}
</style>
<script>
(function(){
  const phone = __PHONE_MODE__;
  document.documentElement.setAttribute('data-new7-phone-low-heat', phone ? 'true':'false');
  if (document.body) document.body.classList.toggle('new7-phone-low-heat', phone);
})();
</script>
"""

REDUCED_MOTION_CSS = r"""
<style>
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation:none!important; transition:none!important; }
}
</style>
"""


def apply_mobile_low_heat_css(st: Any, phone_mode: bool) -> None:
    if phone_mode:
        payload = LOW_HEAT_CSS.replace("__PHONE_MODE__", "true")
    else:
        payload = REDUCED_MOTION_CSS
    st.markdown(payload, unsafe_allow_html=True)


def should_enable_full_autorefresh(state: Mapping[str, Any], page: str, subpage: str) -> bool:
    phone = bool(state.get("phone_mode", False))
    live = bool(state.get("live_data_mode", False) or state.get("live_data_enabled", False) or state.get("ws_enabled", False))
    if phone and not live:
        return False
    if page in {"Settings", "Research", "Other"}:
        return False
    if subpage and subpage not in {"PowerBI Projection"}:
        return False
    return bool(live or not phone)
