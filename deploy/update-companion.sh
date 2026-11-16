#!/usr/bin/env bash
# Cập nhật Companion bản AIRI trên VPS bằng một lệnh (từ 16/11/2026).
#
# Workflow "Peto build" của bản fork PeaGy/peto-airi build bản Peto mỗi lần nhánh `peto` được push và đăng một GitHub
# Release có tệp peto-airi-<thẻ>.tar.gz. Script này tải bản mới nhất (hoặc một thẻ), kiểm tra, giải nén vào một thư mục
# riêng theo thẻ trong THƯ MỤC GỐC (mặc định /home/ubuntu/peto-airi-dist, ngoài repository), rồi đổi symlink `current`
# sang đó trong một bước. PETO_AIRI_DIR trong .env trỏ vào <gốc>/current; máy chủ giải lại symlink ở mỗi yêu cầu nên
# không cần khởi động lại dịch vụ. Giữ bản đang chạy và hai bản khác mới nhất, xóa các bản cũ hơn.
#
# Cách dùng:
#   deploy/update-companion.sh                  tải bản mới nhất (release "latest") và chuyển sang
#   deploy/update-companion.sh --tag <thẻ>      tải đúng release <thẻ>
#   deploy/update-companion.sh --list           các bản trên đĩa, đánh dấu bản đang chạy
#   deploy/update-companion.sh --rollback       quay về bản build ngay trước bản đang chạy
#   deploy/update-companion.sh --from-file <tệp.tar.gz>   cài từ tệp có sẵn (thử tại chỗ, không cần GitHub)
#
# Biến môi trường (đọc từ môi trường, hoặc từ .env ở gốc repository; không bao giờ in ra):
#   PETO_AIRI_RELEASE_TOKEN  token chỉ đọc của GitHub: fine-grained, chỉ repository PeaGy/peto-airi, quyền
#                            "Contents: Read-only". Cần cho mọi lần tải; --list, --rollback, --from-file không cần.
#   PETO_AIRI_RELEASE_REPO   repository phát hành (mặc định PeaGy/peto-airi)
#   PETO_AIRI_DIST_ROOT      thư mục gốc chứa các bản build (mặc định /home/ubuntu/peto-airi-dist)
#   PETO_PYTHON              trình Python để đọc JSON của GitHub (mặc định python3)
#
# Chỉ dùng bash, curl, tar, gzip, sha256sum và công cụ chuẩn. Script không bao giờ xóa gì ngoài thư mục gốc của nó.
set -euo pipefail
umask 022

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd -P)"
ENV_FILE="$REPO_DIR/.env"
KEEP_OTHERS=2
MARKER=".peto-airi-dist"
COMPLETE=".peto-complete"
ASSET_PATTERN='^peto-airi-.*\.tar\.gz$'

die() { printf 'Lỗi: %s\n' "$*" >&2; exit 1; }
say() { printf '%s\n' "$*"; }

# Đọc một biến từ .env mà không in, không source cả tệp (tệp còn khóa khác). Bỏ dấu nháy bao quanh nếu có.
env_value() {
    local name="$1" line value
    [ -r "$ENV_FILE" ] || return 0
    line="$(grep -E "^[[:space:]]*(export[[:space:]]+)?${name}=" "$ENV_FILE" | tail -n 1 || true)"
    [ -n "$line" ] || return 0
    value="${line#*=}"
    value="${value%$'\r'}"
    case "$value" in
        \"*\") value="${value#\"}"; value="${value%\"}" ;;
        \'*\') value="${value#\'}"; value="${value%\'}" ;;
    esac
    printf '%s' "$value"
}

setting() {
    local name="$1" default="$2" value
    value="${!name:-}"
    [ -n "$value" ] || value="$(env_value "$name")"
    printf '%s' "${value:-$default}"
}

usage() {
    sed -n '2,24p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

MODE=latest
TAG=""
FROM_FILE=""
while [ $# -gt 0 ]; do
    case "$1" in
        --list) MODE=list ;;
        --rollback) MODE=rollback ;;
        --tag) [ $# -ge 2 ] || die "--tag cần tên thẻ."; MODE=tag; TAG="$2"; shift ;;
        --from-file) [ $# -ge 2 ] || die "--from-file cần đường dẫn tệp."; MODE=file; FROM_FILE="$2"; shift ;;
        -h|--help) usage; exit 0 ;;
        *) die "Tùy chọn lạ: $1 (xem --help)." ;;
    esac
    shift
done

RELEASE_REPO="$(setting PETO_AIRI_RELEASE_REPO PeaGy/peto-airi)"
ROOT_SETTING="$(setting PETO_AIRI_DIST_ROOT /home/ubuntu/peto-airi-dist)"
PYTHON="$(setting PETO_PYTHON python3)"

valid_name() {
    # Tên thư mục bản build: chữ, số, . _ -, không bắt đầu bằng dấu chấm, không phải "current".
    [[ "$1" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$ ]] && [ "$1" != current ]
}

# ---- Thư mục gốc: kiểm tra trước mọi thao tác ----------------------------------------------------------------------
case "$ROOT_SETTING" in
    /*) ;;
    *) die "PETO_AIRI_DIST_ROOT phải là đường dẫn tuyệt đối (đang là '$ROOT_SETTING')." ;;
esac
mkdir -p "$ROOT_SETTING"
ROOT="$(cd "$ROOT_SETTING" && pwd -P)"
[[ "$ROOT" =~ ^/[^/]+/[^/]+ ]] || die "Từ chối dùng '$ROOT' làm thư mục gốc (quá gần gốc hệ thống)."
case "$ROOT" in
    /home/*/*|/srv/*/*|/c/*|/tmp/*) ;;
    /home/*|/root|/root/*|/usr/*|/etc/*|/var/lib/*|/var/log/*|/bin/*|/sbin/*|/lib/*|/boot/*|/proc/*|/sys/*|/dev/*)
        die "Từ chối dùng '$ROOT' làm thư mục gốc." ;;
esac
[ "$ROOT" != "${HOME:-/nonexistent}" ] || die "Từ chối dùng thư mục nhà làm thư mục gốc."
case "$ROOT/" in
    "$REPO_DIR"/*) die "Thư mục gốc phải nằm ngoài repository ($REPO_DIR)." ;;
esac
case "$REPO_DIR/" in
    "$ROOT"/*) die "Thư mục gốc không được chứa repository." ;;
esac
if [ ! -e "$ROOT/$MARKER" ]; then
    # Chỉ nhận một thư mục rỗng làm gốc mới; thư mục có sẵn tệp khác thì từ chối, để không bao giờ dọn nhầm.
    if [ -n "$(ls -A "$ROOT")" ]; then
        die "'$ROOT' đã có tệp khác và không có dấu $MARKER: không phải thư mục của script này, từ chối dùng."
    fi
    printf 'Thư mục các bản build Companion AIRI, do deploy/update-companion.sh quản lý.\n' > "$ROOT/$MARKER"
fi

# Một lần chạy một lúc (flock có sẵn trên Ubuntu; không có thì bỏ qua).
if command -v flock >/dev/null 2>&1; then
    exec 9>"$ROOT/.lock"
    flock -n 9 || die "Một lần cập nhật khác đang chạy."
fi

current_name() {
    local target
    [ -L "$ROOT/current" ] || return 0
    target="$(readlink "$ROOT/current")"
    printf '%s' "${target##*/}"
}

# Các bản build hoàn chỉnh trên đĩa, cũ trước mới sau (tên thẻ bắt đầu bằng giờ build nên sắp theo tên là theo giờ).
builds() {
    local entry name
    for entry in "$ROOT"/*; do
        name="${entry##*/}"
        valid_name "$name" || continue
        [ -d "$entry" ] && [ ! -L "$entry" ] && [ -e "$entry/$COMPLETE" ] || continue
        printf '%s\n' "$name"
    done | LC_ALL=C sort
}

json_field() {
    # Đọc một trường chuỗi của peto-build.json (tệp do workflow ghi, mỗi trường một dòng) bằng sed.
    sed -n "s/^[[:space:]]*\"$2\"[[:space:]]*:[[:space:]]*\"\\([^\"]*\\)\".*/\\1/p" "$1" | sed -n 1p
}

describe() {
    local name="$1" info="$ROOT/$1/peto-build.json"
    if [ -r "$info" ]; then
        printf '%s (commit %s, build lúc %s)' "$name" "$(json_field "$info" commit | cut -c1-12)" "$(json_field "$info" built_at)"
    else
        printf '%s' "$name"
    fi
}

switch_to() {
    local name="$1"
    valid_name "$name" || die "Tên bản build không hợp lệ: '$name'."
    [ -f "$ROOT/$name/index.html" ] && [ -e "$ROOT/$name/$COMPLETE" ] || die "Bản '$name' không hoàn chỉnh, không chuyển sang."
    # Symlink tương đối, tạo dưới tên tạm rồi đổi tên đè lên `current`: đổi tên là một bước, nên `current` luôn trỏ vào
    # một bản build đã giải nén xong.
    rm -f "$ROOT/.current.new"
    ln -s "$name" "$ROOT/.current.new"
    mv -T "$ROOT/.current.new" "$ROOT/current"
}

prune() {
    local keep current name others=()
    current="$(current_name)"
    mapfile -t others < <(builds | grep -vxF "$current" || true)
    keep=$(( ${#others[@]} - KEEP_OTHERS ))
    [ "$keep" -gt 0 ] || return 0
    for name in "${others[@]:0:$keep}"; do
        # Chỉ xóa thư mục con trực tiếp của gốc, đúng mẫu tên, không phải symlink, không phải bản đang chạy.
        valid_name "$name" && [ "$name" != "$current" ] || continue
        [ -d "$ROOT/$name" ] && [ ! -L "$ROOT/$name" ] || continue
        case "$(cd "$ROOT/$name" && pwd -P)" in
            "$ROOT/$name") ;;
            *) die "Từ chối xóa '$ROOT/$name': không nằm thẳng trong thư mục gốc." ;;
        esac
        rm -rf -- "${ROOT:?}/${name:?}"
        say "Đã xóa bản cũ: $name"
    done
}

report() {
    local current
    current="$(current_name)"
    if [ -n "$current" ]; then
        say "Companion đang chạy: $(describe "$current")"
    else
        say "Chưa có bản nào đang chạy (chưa có symlink $ROOT/current)."
    fi
    local configured
    configured="$(env_value PETO_AIRI_DIR)"
    if [ "$configured" != "$ROOT/current" ]; then
        say "Lưu ý: PETO_AIRI_DIR trong $ENV_FILE chưa là $ROOT/current. Đặt PETO_AIRI_DIR=$ROOT/current rồi"
        say "  sudo systemctl restart peto-web   (chỉ cần một lần; các lần cập nhật sau không phải khởi động lại)."
    fi
}

cleanup_work() {
    [ -n "${WORK:-}" ] || return 0
    case "$WORK" in
        "$ROOT"/.work-*) rm -rf -- "$WORK" ;;
    esac
}

# Kiểm tra tệp nén rồi giải vào một thư mục tạm trong gốc (cùng ổ đĩa, nên đổi tên sau đó là một bước).
# In ra đường dẫn thư mục bản build đã giải (thư mục có index.html).
unpack() {
    local archive="$1" listing verbose top
    [ -s "$archive" ] || die "Tệp '$archive' rỗng hoặc không có."
    gzip -t "$archive" 2>/dev/null || die "Tệp '$archive' không phải gzip hợp lệ (tải hỏng?)."
    # Danh sách ghi ra tệp rồi mới grep: grep -q trong một ống với pipefail có thể làm tar chết vì SIGPIPE và đảo kết quả.
    listing="$WORK/listing.txt"
    verbose="$WORK/listing-verbose.txt"
    tar -tzf "$archive" > "$listing" || die "Không đọc được danh sách tệp trong '$archive'."
    tar -tvzf "$archive" > "$verbose" || die "Không đọc được danh sách tệp trong '$archive'."
    [ -s "$listing" ] || die "Tệp nén rỗng."
    if grep -qE '(^/|(^|/)\.\.(/|$))' "$listing"; then
        die "Tệp nén có đường dẫn tuyệt đối hoặc '..': từ chối."
    fi
    if grep -qE '^[lhcbp]' "$verbose"; then
        die "Tệp nén có symlink, hard link hay tệp đặc biệt: bản build thật không có, từ chối."
    fi
    # Bản build nằm ở gốc tệp nén (./index.html), hoặc trong đúng một thư mục (dist/index.html).
    if grep -qxE '(\./)?index\.html' "$listing"; then
        top=""
    else
        top="$(sed -E 's#^\./##' "$listing" | grep -m 1 -E '^[^/]+/index\.html$' | cut -d/ -f1 || true)"
        [ -n "$top" ] || die "Tệp nén không có index.html."
    fi
    local prefix="${top:+$top/}"
    grep -qxE "(\./)?${prefix//./\\.}peto-build\.json" "$listing" \
        || die "Tệp nén không có peto-build.json (không phải bản do workflow \"Peto build\" làm ra)."
    mkdir "$WORK/x"
    tar -xzf "$archive" -C "$WORK/x" --no-same-owner --no-same-permissions || die "Giải nén thất bại."
    local dir="$WORK/x${top:+/$top}"
    [ -f "$dir/index.html" ] && [ -s "$dir/index.html" ] || die "Sau khi giải nén không thấy index.html."
    [ -f "$dir/peto-build.json" ] || die "Sau khi giải nén không thấy peto-build.json."
    chmod -R u+rwX,go+rX "$dir"
    printf '%s' "$dir"
}

install_dir() {
    # $1: thư mục đã giải, $2: tên bản build. Đổi tên vào gốc rồi chuyển `current`.
    local dir="$1" name="$2"
    valid_name "$name" || die "Tên bản build không hợp lệ: '$name'."
    : > "$dir/$COMPLETE"
    if [ -e "$ROOT/$name" ]; then
        if [ -e "$ROOT/$name/$COMPLETE" ]; then
            say "Bản $name đã có trên đĩa; dùng lại bản đó."
        else
            # Lần chạy trước dừng giữa chừng sau khi đổi tên (không xảy ra với mv, nhưng phòng hờ): thay bằng bản mới.
            rm -rf -- "${ROOT:?}/${name:?}"
            mv -T "$dir" "$ROOT/$name"
        fi
    else
        mv -T "$dir" "$ROOT/$name"
    fi
    switch_to "$name"
    say "Đã chuyển Companion sang $name."
    prune
}

# ---- GitHub --------------------------------------------------------------------------------------------------------
TOKEN=""
api() {
    # $1: đường dẫn API, $2: tệp ghi ra. Token đi qua stdin của curl, không nằm trên dòng lệnh, không vào nhật ký.
    printf 'header = "Authorization: Bearer %s"\n' "$TOKEN" | curl --config - -fsS --proto '=https' \
        --retry 3 --retry-delay 2 --connect-timeout 20 \
        -H "Accept: application/vnd.github+json" -H "X-GitHub-Api-Version: 2022-11-28" \
        -H "User-Agent: peto-update-companion" -o "$2" "https://api.github.com$1"
}

download_asset() {
    # $1: id tệp của release, $2: tệp ghi ra. GitHub trả 302 tới một địa chỉ ký sẵn trên máy chủ tải; đi theo chuyển
    # hướng bằng tay để token chỉ gửi cho api.github.com, không bao giờ cho máy chủ tải.
    local location
    location="$(printf 'header = "Authorization: Bearer %s"\n' "$TOKEN" | curl --config - -sS --proto '=https' \
        --retry 3 --retry-delay 2 --connect-timeout 20 -o /dev/null -w '%{redirect_url}' \
        -H "Accept: application/octet-stream" -H "X-GitHub-Api-Version: 2022-11-28" \
        -H "User-Agent: peto-update-companion" "https://api.github.com/repos/$RELEASE_REPO/releases/assets/$1")" \
        || return 1
    case "$location" in
        https://*) ;;
        *) return 1 ;;
    esac
    curl -fsSL --proto '=https' --proto-redir '=https' --retry 3 --retry-delay 2 --connect-timeout 20 \
        -H "User-Agent: peto-update-companion" -o "$2" "$location"
}

release_info() {
    # In: thẻ, id tệp, cỡ, digest (mỗi thứ một dòng) của tệp peto-airi-*.tar.gz trong release.
    "$PYTHON" -I -c '
import json, re, sys
release = json.load(open(sys.argv[1], encoding="utf-8"))
assets = [a for a in release.get("assets", []) if re.match(sys.argv[2], a.get("name", ""))]
if len(assets) != 1:
    sys.exit(1)
asset = assets[0]
print(release.get("tag_name", ""))
print(asset["id"])
print(asset.get("size", 0))
print(asset.get("digest") or "")
' "$1" "$ASSET_PATTERN"
}

fetch_release() {
    TOKEN="$(setting PETO_AIRI_RELEASE_TOKEN "")"
    [ -n "$TOKEN" ] || die "Thiếu PETO_AIRI_RELEASE_TOKEN (trong môi trường hoặc $ENV_FILE). Xem docs/notes/companion.md."
    command -v "$PYTHON" >/dev/null 2>&1 || die "Không thấy '$PYTHON' để đọc JSON của GitHub (đặt PETO_PYTHON)."
    local path
    if [ "$MODE" = tag ]; then
        valid_name "$TAG" || die "Thẻ không hợp lệ: '$TAG'."
        path="/repos/$RELEASE_REPO/releases/tags/$TAG"
    else
        path="/repos/$RELEASE_REPO/releases/latest"
    fi
    api "$path" "$WORK/release.json" \
        || die "Không đọc được release từ GitHub ($RELEASE_REPO). Token sai, hết hạn, thiếu quyền, hay chưa có release?"
    local info name asset_id size digest
    info="$(release_info "$WORK/release.json" 2>/dev/null | tr -d '\r')" \
        || die "Release không có đúng một tệp peto-airi-*.tar.gz (hoặc JSON của GitHub lạ)."
    { read -r name; read -r asset_id; read -r size; read -r digest; } <<< "$info"
    [[ "$asset_id" =~ ^[0-9]+$ && "$size" =~ ^[0-9]+$ ]] || die "JSON của release không có id hay cỡ tệp hợp lệ."
    valid_name "$name" || die "Thẻ release không hợp lệ: '$name'."
    if [ "$(current_name)" = "$name" ]; then
        say "Bản mới nhất ($name) đang chạy rồi; không có gì để làm."
        return 1
    fi
    if [ -e "$ROOT/$name/$COMPLETE" ]; then
        say "Bản $name đã có trên đĩa; chuyển sang mà không tải lại."
        switch_to "$name"
        prune
        return 1
    fi
    say "Đang tải $name (${size} byte)…"
    download_asset "$asset_id" "$WORK/build.tar.gz" \
        || die "Tải tệp của release $name thất bại."
    [ "$(wc -c < "$WORK/build.tar.gz" | tr -d ' ')" = "$size" ] || die "Tệp tải về không đúng cỡ ${size} byte."
    case "$digest" in
        sha256:*)
            [ "$(sha256sum "$WORK/build.tar.gz" | cut -d' ' -f1)" = "${digest#sha256:}" ] \
                || die "Mã băm SHA-256 của tệp tải về không khớp với GitHub."
            ;;
    esac
    RELEASE_NAME="$name"
    return 0
}

# ---- Chạy ----------------------------------------------------------------------------------------------------------
case "$MODE" in
    list)
        current="$(current_name)"
        found=0
        while IFS= read -r name; do
            [ -n "$name" ] || continue
            found=1
            if [ "$name" = "$current" ]; then mark="*"; else mark=" "; fi
            say "$mark $(describe "$name")"
        done < <(builds)
        [ "$found" = 1 ] || say "Chưa có bản build nào trong $ROOT."
        [ -z "$current" ] || [ -e "$ROOT/$current/$COMPLETE" ] || say "Cảnh báo: current trỏ vào '$current', không phải bản hoàn chỉnh."
        exit 0
        ;;
    rollback)
        current="$(current_name)"
        [ -n "$current" ] || die "Chưa có bản nào đang chạy."
        previous="$(builds | awk -v c="$current" '$0 < c' | tail -n 1)"
        [ -n "$previous" ] || die "Không có bản build nào cũ hơn $current để quay về."
        switch_to "$previous"
        say "Đã quay về $previous (bản $current vẫn còn trên đĩa)."
        report
        exit 0
        ;;
esac

WORK="$(mktemp -d "$ROOT/.work-XXXXXX")"
trap cleanup_work EXIT
# Thư mục tạm của lần chạy trước bị ngắt (máy tắt giữa chừng): dọn đi, chỉ những thư mục .work-* trong gốc.
for stale in "$ROOT"/.work-*; do
    [ -d "$stale" ] && [ "$stale" != "$WORK" ] && rm -rf -- "$stale"
done

if [ "$MODE" = file ]; then
    [ -f "$FROM_FILE" ] || die "Không thấy tệp '$FROM_FILE'."
    dir="$(unpack "$FROM_FILE")"
    name="$(json_field "$dir/peto-build.json" tag)"
    if [ -z "$name" ]; then
        name="peto-$(date -u +%Y%m%d-%H%M%S)-local"
    fi
    valid_name "$name" || die "Thẻ trong peto-build.json không hợp lệ: '$name'."
    if [ "$(current_name)" = "$name" ]; then
        say "Bản $name đang chạy rồi; không có gì để làm."
    else
        install_dir "$dir" "$name"
    fi
else
    RELEASE_NAME=""
    if fetch_release; then
        dir="$(unpack "$WORK/build.tar.gz")"
        install_dir "$dir" "$RELEASE_NAME"
    fi
fi
report
