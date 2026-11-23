# Omdrop for Flea

**Recommended:** If you don’t mind waiting for a large Rust build, install [Flea’s native Omdrop integration (PR #468)](https://github.com/thisisgm/flea/pull/468). On Apple Silicon, it lets you send files from Flea’s **AirDrop** menu, see transfer progress inside Flea, and manage receiving in **Settings → Plugins → AirDrop**. You don’t need this standalone plugin with that build.

Ask your coding agent:

> Build and install https://github.com/thisisgm/flea/pull/468 locally for the full Omdrop integration.

**Prefer stock Flea without a rebuild?** Install the standalone plugin below. It adds a separate **Omdrop** entry to the file menu and **Settings → Plugins** in Flea 0.4.3, and leaves the built-in AirDrop settings unchanged, but unusable on a Mac.

## Install on Omarchy or Arch Linux

Install and configure [Omdrop](https://github.com/netmojo-systems/omdrop-plugin) and its supported radio driver first. You need a working `omdrop` CLI, a systemd user session and a desktop notification service.

Download `flea-omdrop-0.1.0-1-any.pkg.tar.zst` and `SHA256SUMS` from the [release](https://github.com/netmojo-systems/flea-omdrop/releases/tag/v0.1.0). In the download directory:

```sh
sha256sum -c SHA256SUMS
sudo pacman -U ./flea-omdrop-0.1.0-1-any.pkg.tar.zst
flea plugin add /usr/share/flea-omdrop
flea plugin enable netmojo.omdrop
```

This is a prebuilt, architecture-independent Arch package. The adapter uses Python’s standard library; there is no compiler, pip install or venv step. Pacman updates the shared runtime. Register the plugin separately for each Flea user. If a future release changes the manifest, follow that release’s registration instructions.

### Install from Git instead

With `flea`, `omdrop`, Python 3, systemd, util-linux and `notify-send` installed:

```sh
flea plugin add https://github.com/netmojo-systems/flea-omdrop.git
flea plugin enable netmojo.omdrop
```

Use `flea plugin update netmojo.omdrop` for Git installs only. Choose one installation method; both use the same plugin ID. To switch, first run `flea plugin remove netmojo.omdrop`.

## Send files

1. Turn on Omdrop and make the receiving device discoverable.
2. Select local files in Flea and open their file menu. If discovery has just started, reopen the menu after nearby devices have had time to answer.
3. Choose the receiver under **Omdrop**. Discovery uses device addresses as target IDs, not display names.

**Queued** means the systemd user manager started a separate send job, not that the receiver accepted. You can close Flea or leave the prompt open beyond Flea’s 30-second plugin deadline. When Omdrop reports byte counts, one desktop notification shows the file name or file count, percentage, and bytes read for upload. Even 100% is not a delivery receipt. Omdrop’s final result replaces the progress notification; sends without byte counts report only their outcome. Disabling the plugin does not cancel a queued send. Omdrop and the receiver still enforce their own timeouts.

## Remove

```sh
flea plugin remove netmojo.omdrop
# For the Arch package only:
sudo pacman -R flea-omdrop
```
