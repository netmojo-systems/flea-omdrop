# Maintainer: netmojo <56850867+netmojo@users.noreply.github.com>
pkgname=flea-omdrop
pkgver=0.1.0
pkgrel=1
pkgdesc='Omdrop send target for the Flea file manager'
arch=(any)
url='https://github.com/netmojo-systems/flea-omdrop'
license=(MIT)
depends=('flea>=0.4.3' 'omdrop>=0.18.12' python systemd libnotify)
PKGEXT='.pkg.tar.zst'

package() {
    local file
    for file in discovery.py delivery.py; do
        install -Dm644 "$startdir/$file" "$pkgdir/usr/lib/$pkgname/$file"
    done
    install -Dm755 "$startdir/plugin.py" "$pkgdir/usr/lib/$pkgname/plugin.py"
    install -Dm755 "$startdir/packaging/run" "$pkgdir/usr/share/$pkgname/plugin.py"
    install -Dm644 "$startdir/manifest.json" "$pkgdir/usr/share/$pkgname/manifest.json"
    install -Dm644 "$startdir/LICENSE" "$pkgdir/usr/share/licenses/$pkgname/LICENSE"
    install -Dm644 "$startdir/README.md" "$pkgdir/usr/share/doc/$pkgname/README.md"
}
