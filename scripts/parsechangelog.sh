#!/usr/bin/env bash
#
# FILE: parsechangelog.sh
# DESCRIPTION: Extract version and release notes from CHANGELOG.md
# USAGE: Used by github actions to receive release notes and tag for releasing
# LICENSE: GPLv3
# DATE: 2026-07-01

#######################################
# -e: exit script if any command has non-zero exit status
# -u: catch typo/undefined variables
# -x: debug purpose; printing every executed commands
#######################################
set -eu

#######################################
# -o pipefail: prevents errors in a pipeline from being masked.
#              basically, make sure to exit via nonzero exit code
#              when error occur. We can also say that if one command fail
#              script fail instead of masked.
#######################################
set -o pipefail

#######################################
# CONSTANTS
#
# readonly: immutable/unchangeable variables
#
# $1: first argument passed to the script like sys.argv[1]
#     ./script.sh test.md -> $1 == test.md
#
# `:-`: if $1 is missing or empty, use string on the right
#######################################
readonly CHANGELOG_FILE="${1:-CHANGELOG.md}"
readonly GITHUB_OUTPUT="${GITHUB_OUTPUT:-/dev/stdout}"

# globals
version=""
notes=""

#######################################
# Validate CHANGELOG.md exist
# Globals:
#   CHANGELOG_FILE
# Arguments:
#   [[]]: bash modern test syntax.
#   -f: built-in flag that checks if a file exist.
#   !: means NOT like `if not` on python
# Returns:
#   1 if file doesn't exist
#######################################
is_changelog_file_exist() {
  if [[ ! -f "$CHANGELOG_FILE" ]]; then
    echo "::error::CHANGELOG.md not found at $CHANGELOG_FILE"
    exit 1
  fi
}

#######################################
# Extract version from the first valid header
# Globals:
#   version
#   GITHUB_OUTPUT
# Arguments:
#   None – reads $CHANGELOG_FILE
# Returns:
#   Sets global `version`, writes to GITHUB_OUTPUT, exits if none found
#######################################
extract_version() {
  # local constant to use only in function
  local first_header

  # regex magic
  # Extract the first version header from CHANGELOG.md
  # Supports:
  #   ## [Unreleased]
  #   ## [1.2.3]
  #   ## [1.2.3-alpha]
  #
  # $(): command substitution; it runs the command inside the parentheses
  #      and saves the output to the first_header
  #
  # grep: linux grep tool; -m 1 tells to stop after finding the first match
  #
  # ||: OR. Try the first grep command, if it fails then try second one.
  # ||true: prevents the script from crashing due to `set -e` rule
  #         because grep returns exit code 1 if nothing found
  #
  # `^`: means start of line regex
  # `\[`: means literal `[`
  # `'^## \['`: means `## [`,
  #
  if ! first_header=$(grep -m 1 '^## \[' "$CHANGELOG_FILE"); then
    echo "::error::No version header found in CHANGELOG.md"
    exit 1
  fi

  # BASH_REMATCH is filled automatically after =~ succeeds.
  # [0] = whole matched string
  # [1] = first (...) capture group
  #
  # Format: `## [version] - 2026-07-01`
  if [[ "$first_header" =~ ^\#\#\ \[([0-9]+\.[0-9]+\.[0-9]+[^]]*)\] ]]; then
    version="${BASH_REMATCH[1]}"
  # Format: `## [Unreleased]`
  elif [[ "$first_header" =~ ^\#\#\ \[([Uu]nreleased)\] ]]; then
    version="${BASH_REMATCH[1]}"
  else
    echo "::error::Invalid version format in: $first_header"
    echo "::error::Expected: '## [X.Y.Z]' or '## [X.Y.Z-alpha] - 2026-07-01'"
    exit 1
  fi

  echo "version=$version" >>"$GITHUB_OUTPUT"
  echo "::notice::Detected version: $version"
}

#######################################
# Check if version is "Unreleased"
# Globals:
#   version
#   GITHUB_OUTPUT
# Arguments:
# >>: append redirection; it takes whatever echo prints and adds it to
#     the bottom of the file specified by $GITHUB_OUTPUT
#######################################
is_version_unreleased() {
  if [[ "$version" =~ ^[Uu]nreleased$ ]]; then
    echo "is_unreleased=true" >>"$GITHUB_OUTPUT"
    echo "::notice:Version is Unreleased, skipping release creation"
    exit 0
  fi

  echo "is_unreleased=false" >>"$GITHUB_OUTPUT"
}

#######################################
# Extract the changelog notes for the specific version using awk
# Globals:
#   notes
# Arguments:
#   version (global) – used inside awk via -v
# Returns:
#   Sets global `notes` with the content between version headers
#######################################
extract_change_notes() {
  notes=$(awk -v ver="$version" '
    BEGIN { found=0; capture=0; notes=""; }

    # when we hit ANY bracketed header
    /^## \[/ {
        # if it is OUR version, start capturing
        if (!found && index($0, ver) > 0) {
          found=1;
          capture=1;
          next;
        # if we were capturing and hit a new header, stop capturing
        } else if (capture==1) {
          capture=0;
        }
    }

    # if capture is true, append the line
    capture==1 { notes = notes $0 "\n"; }

    # print the final result
    END { print notes; }
  ' "$CHANGELOG_FILE")
}

#######################################
# Format as a multiline string for GitHub Actions
# Globals:
#   notes
#   GITHUB_OUTPUT
#   eof – unique delimiter generated with random bytes and base64
#         creates a delimeter like dGhpc2lzYXNhbXBsZQo
#         basically, act as a random marker
#
# EXPLANATION:
#   github action support special syntax
#   instead of key=value, you write:
#     key<<DELIMITER
#     line 1
#     line 2
#     ...
#     DELIMITER
#
#   and runner reads everything between delimeter.
#
# Returns:
#   Writes notes to GITHUB_OUTPUT using heredoc syntax
#######################################
convert_and_save_to_github_output() {
  # example:
  #   notes<<dGhpc2lzYXNhbXBsZQo=
  # - Added cool feature
  # - Fixed nasty bug
  # dGhpc2lzYXNhbXBsZQo=
  # The <<$eof … $eof block tells the runner to treat the text between them as one big string, newlines and all.
  #
  eof=$(dd if=/dev/urandom bs=15 count=1 status=none | base64)
  {
    echo "notes<<$eof"
    echo "$notes"
    echo "$eof"
  } >>"$GITHUB_OUTPUT"

  # debug output
  echo "Release notes excerpt:"
  echo "$notes" | head -10
}

#######################################
# Main execution flow
#
# 1. Validate changelog exists.
# 2. Extract latest version.
# 3. Exit early if version is Unreleased.
# 4. Extract release notes.
# 5. Export values for GitHub Actions.
#######################################
main() {
  is_changelog_file_exist
  extract_version
  is_version_unreleased
  extract_change_notes
  convert_and_save_to_github_output
}

# execute main
main "$@"
