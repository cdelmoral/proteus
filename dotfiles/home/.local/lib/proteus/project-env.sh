# Sourced at the provider's project-command boundary, never around its runtime.
# Keep shims rather than a concrete Node prefix so cd resolves again each time.
export PATH="$HOME/.local/bin:$HOME/.local/share/mise/shims:${PATH:-/usr/local/bin:/usr/bin:/bin}"
