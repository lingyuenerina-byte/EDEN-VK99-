# EDEN 构建环境: 禁代理 + MSVC 变量(不覆盖 bash PATH) + cargo
export PATH="$HOME/.cargo/bin:$PATH"
export CARGO_HTTP_PROXY= HTTP_PROXY= HTTPS_PROXY= ALL_PROXY= http_proxy= https_proxy= all_proxy=
_tmpv=$(mktemp)
/c/Users/Lingy/vk99screen/vcvars-dump.bat | tr -d '\r' > "$_tmpv"
while IFS='=' read -r k v; do
  case "$k" in
    INCLUDE|LIB|LIBPATH|Platform|VSVER|WindowsSdkDir|WindowsSDKVersion|UCRTVersion|VCToolsInstallDir|VCToolsRedistDir) export "$k=$v";;
  esac
done < "$_tmpv"
rm -f "$_tmpv"
# MSVC x64 编译器 bin 追加进 bash PATH (POSIX 化路径给 which/git-bash 用)
if [ -n "$VCToolsInstallDir" ]; then
  _msvc="$(echo "${VCToolsInstallDir}bin/Hostx64/x64" | sed 's/\\/\//g; s/^D:/\/d/')"
  export PATH="$PATH:$_msvc"
fi
which cl link cargo >/dev/null 2>&1 && echo "ENV-OK: cl+link+cargo 就绪" || echo "ENV-WARN: 检查 vcvars/rustup"
