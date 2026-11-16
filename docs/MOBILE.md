# AI Agent Village as an app — desktop and Android

The Village is one Progressive Web App (PWA). You install the same app on the Ubuntu desktop
and on your Android phone. The phone reaches your PC only through **Tailscale**, a private
network between your own devices. The Village server keeps listening on `127.0.0.1` only.

> **What was tested and what was not**
> - Tested by Claude Code, in a headless Chrome on this PC: the app passes Chrome's
>   installability check, the phone layout at 390 px, the offline page, the update notice.
> - **Not tested by Claude Code: Tailscale, anything on a real Android phone, and clicking
>   "Install" in a real Chrome window.** Claude Code cannot install Tailscale or use a phone.
>   The Tailscale commands below were copied from Tailscale's official documentation on
>   2026-11-16. If a step behaves differently, trust what Tailscale shows you.

Before you start, update the Village once (new database migration and a new frontend build):

```bash
./village stop && ./village setup && ./village start
./village doctor
```

`doctor` must show `PASS  bind: port 8000 is listening on 127.0.0.1 only`.

## a) Desktop (Ubuntu, Chrome)

1. Start the Village: `./village start`.
2. Open <http://127.0.0.1:8000> in Chrome and log in.
3. Open the Chrome menu **⋮** and choose **"Install AI Agent Village…"**. Depending on the Chrome
   version it is under **⋮ → Cast, save and share → "Install page as app…"**, or shown as a
   small install icon at the right end of the address bar. The login page also shows a quiet
   **"Install app"** button when Chrome offers it.
4. The Village opens in its own window with the house-robot icon and appears in your app menu.

The installed app is only a window. **It does not start the server.** If the server is not
running, the app shows "Village is unreachable". Start it with `./village start`.

**The old launcher.** You may have `~/.local/share/applications/agent-village.desktop`
("Start the village and open it"). It starts the server, which the installed app cannot do, so
you may want to keep it. If you still want to remove it:

```bash
rm ~/.local/share/applications/agent-village.desktop
```

To uninstall the app itself: open it, **⋮ → "Uninstall AI Agent Village…"**.

## b) Tailscale on the PC

1. Create a free Tailscale account at <https://tailscale.com> (you choose the login provider).
2. Install Tailscale on Ubuntu with the official install command, then connect:

   ```bash
   curl -fsSL https://tailscale.com/install.sh | sh
   sudo tailscale up
   ```

   `tailscale up` prints a link. Open it and log in.
3. Turn on HTTPS for your tailnet (needed once): open the **DNS** page of the Tailscale admin
   console, enable **MagicDNS** if it is off, and under **HTTPS Certificates** choose
   **Enable HTTPS**.
   Note: this publishes your PC's Tailscale name (for example `my-pc.tail1234.ts.net`) in a
   public certificate log. The name is public, the Village is not. If the PC's name contains
   something private, rename the machine in the admin console first.
4. Share the Village inside your tailnet. The Village must be running.

   ```bash
   tailscale serve --bg 8000
   ```

   If it refuses for lack of permission, run it once with `sudo`.
5. Find the address. It is printed by the command above and again by:

   ```bash
   tailscale serve status
   ```

   It looks like `https://my-pc.tail1234.ts.net`.
6. Tell the Village that this name is allowed. Open `data/.env` in an editor and add one line
   (use your own name, without `https://`):

   ```
   VILLAGE_ALLOWED_HOSTS=127.0.0.1,localhost,my-pc.tail1234.ts.net
   ```

7. Restart and check:

   ```bash
   ./village restart
   ./village doctor
   ```

   `doctor` shows `hosts: VILLAGE_ALLOWED_HOSTS allows … (remote name: my-pc.tail1234.ts.net)`
   and still `bind: … 127.0.0.1 only`.

Without step 6 the Village answers the Tailscale name with "Invalid Host header". That is the
protection working, not a fault.

## c) Android

1. Install the **Tailscale** app from Google Play and log in with the **same account**.
   Leave it connected.
2. Open Chrome on the phone and go to your address, for example
   `https://my-pc.tail1234.ts.net`.
3. Log in with your Village username and password.
4. Chrome menu **⋮ → "Add to Home screen" → "Install"** (some versions say **"Install app"**).
5. Open the Village from the home screen. Overview, Tasks, Agents and More are at the bottom.

## d) Limits

- The PC must be **on**, **awake**, and the Village must be **running**. Tailscale must be
  connected on both devices. Otherwise the phone shows "Village is unreachable — check that the
  PC is on and Tailscale is connected". Nothing is stored on the phone, so nothing can be
  shown offline.
- The header shows **Online** or **Offline**. It checks every 30 seconds while the app is open
  and visible.
- Desktop and phone are logged in separately. Each appears under
  **More → Application Settings → Devices & sessions**.
- A login lasts 7 days.
- To turn remote access **off**:

  ```bash
  tailscale serve reset
  ```

  You can also remove the name from `VILLAGE_ALLOWED_HOSTS` and run `./village restart`.

## e) Security

- **Never use `tailscale funnel`.** Funnel puts the address on the public internet. `serve`
  keeps it inside your own devices.
- Do not share your tailnet or this machine with other people's accounts. Everyone who can
  reach the address sees the Village's login page.
- Keep the admin password long and unique. After 5 wrong passwords a username is locked for
  5 minutes, and that now survives a restart.
- Lost or sold a phone? On the PC open **Application Settings → Devices & sessions** and press
  **Revoke** for it, or **Log out all other devices**. Also remove the phone from your tailnet
  in the Tailscale admin console.
- The Village never listens on the network itself. Do not change `VILLAGE_HOST`, do not set up
  port forwarding on your router, and do not put another proxy in front of it.
- The session cookie is `HttpOnly` and `SameSite=Strict`, and also `Secure` when you come in
  over the Tailscale HTTPS address.
