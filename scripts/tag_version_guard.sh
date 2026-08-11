#!/bin/sh
# SPDX-FileCopyrightText: Copyright (C) 2026 unlucio and the Bespok3d contributors
# SPDX-License-Identifier: GPL-3.0-only
# Guard: a `plugin-<name>-v<version>` release tag must name a plugin this repo holds, at the exact
# version that plugin's manifest declares.
#
# The release workflow fires on the tag, but everything it publishes is stamped from manifest.json:
# the package filename, the GitHub release, and the index atom the app reads to learn a newer
# version exists. A tag whose number disagrees therefore publishes a package the tag lies about, and
# the disagreement is invisible afterwards. Refuse the run instead.
#
# Refusing a ref that is not a release tag at all is the same guard from the other side: that is
# what a run off a branch looks like, and a branch must never publish.
set -eu

ref_name="${1:-}"

case "$ref_name" in
    plugin-*-v*) ;;
    *)
        echo "'$ref_name' is not a plugin-<name>-v<version> tag: a release is published by a" \
             "version tag and by nothing else" >&2
        exit 1
        ;;
esac

claimed_name="${ref_name#plugin-}"
claimed_name="${claimed_name%-v*}"
claimed_version="${ref_name##*-v}"

declared_version=""
for manifest in manifest.json */manifest.json */*/manifest.json; do
    [ -f "$manifest" ] || continue
    [ "$(jq -r '.name' "$manifest")" = "$claimed_name" ] || continue
    declared_version="$(jq -r '.version' "$manifest")"
    break
done

if [ -z "$declared_version" ]; then
    echo "tag '$ref_name' names plugin '$claimed_name', which this repo does not hold" >&2
    exit 1
fi

if [ "$claimed_version" != "$declared_version" ]; then
    echo "tag '$ref_name' claims $claimed_version but $claimed_name declares $declared_version:" \
         "the package would be published as $declared_version" >&2
    exit 1
fi

echo "tag '$ref_name' matches the version $claimed_name declares: $declared_version"
