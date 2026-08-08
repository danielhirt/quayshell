# Quayshell Zsh integration. The outer login shell loads the login environment.
[[ -r "$HOME/.zshrc" ]] && source "$HOME/.zshrc"

__quayshell_preexec() {
    printf '\e]666;vte.ext.quayshell.shell.preexec!\e\\\e]133;C\e\\\r'
}

__quayshell_precmd() {
    local exit_code="$?"
    printf '\e]666;vte.ext.quayshell.shell.postexec=%s\e\\' "$exit_code"
    printf '\e]133;D;%s\e\\\e]133;A\e\\' "$exit_code"
    return "$exit_code"
}

autoload -Uz add-zsh-hook
add-zsh-hook preexec __quayshell_preexec
add-zsh-hook precmd __quayshell_precmd
PS1="${PS1}"$'%{\e]133;B\e\\%}'
ZDOTDIR="$HOME"
