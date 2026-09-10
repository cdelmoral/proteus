case $- in
  *i*) ;;
  *) return ;;
esac

export PATH="$HOME/.local/bin:$PATH"
eval "$("$HOME/.local/bin/mise" activate bash)"
export PNPM_HOME="$HOME/.local/share/proteus/pnpm/current"
export PATH="$PNPM_HOME:$PATH"

eval "$(starship init bash)"
