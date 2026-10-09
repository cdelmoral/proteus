case $- in
  *i*) ;;
  *) return ;;
esac

export PATH="$HOME/.local/bin:$PATH"
eval "$("$HOME/.local/bin/mise" activate bash)"

eval "$(fzf --bash)"

eval "$(starship init bash)"
