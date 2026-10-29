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

# Resolve at execution time, including after cd and when a version is missing.
# PATH activation can leave another Node executable available on a missing version.
eval "$("$HOME/.local/bin/mise" activate bash --shims)"
# pnpm is installed once in the baseline npm prefix; its env-node entry point
# must use the selected Node rather than require pnpm in every Node installation.
export PATH="$HOME/.local/bin:$PATH"

eval "$(fzf --bash)"

eval "$(starship init bash)"
