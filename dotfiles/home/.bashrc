case $- in
  *i*) ;;
  *) return ;;
esac

export PATH="$HOME/.local/bin:$PATH"

github_token_file="$HOME/.local/share/proteus/secrets/github-token"
if [[ -r "$github_token_file" ]]; then
  GH_TOKEN="$(<"$github_token_file")"
  export GH_TOKEN
fi
unset github_token_file

eval "$("$HOME/.local/bin/mise" activate bash)"

eval "$(starship init bash)"
