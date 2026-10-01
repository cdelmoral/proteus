case $- in
  *i*) ;;
  *) return ;;
esac

export PATH="$HOME/.local/bin:$PATH"

# shellcheck source=dotfiles/home/.local/lib/proteus/credentials.sh
source "$HOME/.local/lib/proteus/credentials.sh"
github_token_file="$(proteus_github_token_file)"
unset -f proteus_github_token_file
if [[ -r "$github_token_file" ]]; then
  GH_TOKEN="$(<"$github_token_file")"
  export GH_TOKEN
fi
unset github_token_file

eval "$("$HOME/.local/bin/mise" activate bash)"

eval "$(starship init bash)"
