# Play Warband together: Mac and Windows

One of you creates a room; the other joins with its code. You play against
each other in a two-player real-time match. Both players need Warband
**0.1.0-preview.3** and an internet connection. There is no account to create.

**Preview.3 is being prepared.** Its download links below will become
available after package verification and publication. The currently published
release is [preview.2](https://github.com/ikamensh/saga2d/releases/tag/warband-v0.1.0-preview.2).

## 1. Open the game on your Mac

**On Ilya's Mac:** open **Warband** from the Dock or **Finder → Applications →
Warband**. Updates use the existing `/Applications/Warband.app` location.
The preview.3 installation will be confirmed when its package is ready.

For a fresh installation on another **Apple Silicon Mac** (M1 or later):

1. Download the [Mac app](https://github.com/ikamensh/saga2d/releases/download/warband-v0.1.0-preview.3/Warband-0.1.0-preview.3-darwin-arm64-app.zip).
2. In Finder, open **Downloads** and double-click the ZIP to extract
   **Warband.app**.
3. Drag **Warband.app** into **Applications** in the Finder sidebar. Replace
   an older copy if you are updating it.
4. Double-click **Warband.app**. The title screen has a **Multiplayer** button.
   For later sessions, open this installed copy; you can keep it in the Dock.

This preview is not notarized. If macOS blocks the first launch because it
cannot verify the developer, open **System Settings → Privacy & Security**,
find the Warband message, choose **Open Anyway**, then confirm **Open**.
This is the app-specific first-launch procedure described by
[Apple](https://support.apple.com/en-us/102445). An alert saying the app is
damaged or contains malware is a different problem; see troubleshooting below.

## 2. Your friend installs the Windows version

This download is for a Windows 10/11 PC with x64 application support.

1. Download the [Windows installer](https://github.com/ikamensh/saga2d/releases/download/warband-v0.1.0-preview.3/Warband-0.1.0-preview.3-windows-x64-setup.exe).
2. Open the downloaded **Warband-0.1.0-preview.3-windows-x64-setup.exe**.
3. Follow the installer with its default folder. A desktop shortcut is
   optional. Leave **Play Warband** selected on the last page to open the game.
4. For later sessions, open Start, type **Warband**, and select it.

Everything needed to run the game is included. The installer installs for
your Windows account.

The preview installer is unsigned. If the first launch shows **Windows
protected your PC**, and you downloaded the file linked above, choose
**More info → Run anyway**, if offered. Microsoft describes that
[SmartScreen prompt](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/publish-first-app).
If Windows offers no option to proceed, see the separate Smart App Control
case below.

## 3. Create and join your match

Use your usual chat or call to share the code. Either of you can create the
room; these steps use the Mac player as the creator.

1. **Both players:** click **Multiplayer** on the title screen. Leave
   **Online · selected** as it is.
2. **Mac player:** click **Create room**. Wait for **Waiting for your partner**
   and **Room code: …**. Click **Copy room code**, paste it into your chat with
   your friend, and send it. Leave the game open on this screen.
3. **Windows player:** copy that code from the chat, click **Paste code** in
   Warband, then click **Join room**. You can also enter the code by hand;
   letter case does not matter. The keyboard paste shortcut is **Ctrl+V** on
   Windows or **Cmd+V** on a Mac.
4. **Both players:** the match opens automatically when the second player
   connects. There is no separate Ready or Start button, so be ready to play
   before joining.

You each control a different settlement, starting in opposite parts of the
map with a Town Hall and three peasants. The other settlement begins hidden
by fog; explore to find it. The two seats are for you and your friend, with
no extra AI player in this room. Each new room generates a fresh map with
meadows, groves, ponds and rocky regions. The stone rim marks the edge of the
playable map; dark fog hides places you have not explored.

## 4. Your first few minutes

Use left-click to select, then right-click to give an order. On a Mac
trackpad, a two-finger click or Control-click gives the right-click order.

Peasants automatically gather needed gold and lumber when they have no other
job. They choose resources and routes your faction knows about, avoiding
known danger. You can leave routine gathering to them and focus on building
and soldiers, or give a specific gathering order yourself.

1. Select one **Peasant** and right-click the nearby **Gold Mine**. The
   peasant enters it, then returns with gold automatically.
2. Send another peasant to a tree for lumber. The worker chops and carries
   the wood back automatically. Gold and lumber totals are at the top.
3. Select a peasant, click **Build**, then **Farm**, and click a clear patch
   of ground. The shortcut is **B**, then **F**. A green placement outline
   means the location is valid. Let that peasant finish construction.
4. Build a **Barracks** the same way: **B**, then **B**. When it is finished,
   select it and click **Footman** or press **F** to train a soldier.
5. Keep gathering. Select the **Town Hall** and click **Peasant** or press
   **P** to train another worker. Build more farms when supply is full.
6. Select your soldiers, press **A**, then click towards the enemy. This
   attack-move order fights enemies along the route. Right-clicking empty
   ground gives a movement order instead.

The command buttons change with your selection. Hover over them to see costs
and prerequisites. A greyed-out action may need resources, supply, a completed
building, or a prerequisite. Your aim is to eliminate **all enemy units and
buildings**.

Your orders take priority over automatic work. Workers complete manual and
Shift-queued orders before looking for another gathering job, including after
finishing construction. To keep a worker where you put it, select it and use
**Stop (S)** or **Hold (H)**; this switches off its automatic work until you
give it another order. A worker with no known safe work may wait for you to
explore or clear the route.

## Useful controls

| What you want to do | Control |
| --- | --- |
| Select several units | Drag a box; Shift-click adds to the selection |
| Select the same unit type on screen | Double-click one of those units |
| Find an idle worker | Tab, or the **Idle** button |
| Give the usual order | Right-click: move, mine, chop, attack, repair or resume construction |
| Queue another order | Hold Shift while giving it |
| Attack-move / stop / hold position | A, then a destination / S / H |
| Park a worker without automatic gathering | S or H; another order enables automatic work again |
| Set where new units gather | Select their training building, then right-click a destination |
| Move the camera | Arrow keys, screen edges, or left-click the minimap |
| Return to your base | Home or Backspace; the Mac Delete key sends Backspace |
| Zoom | Mouse wheel or trackpad scroll; + and − also work |
| Jump to the latest alert | Space |
| Open the menu directly | F10 |
| Cancel a command, deselect, then open the menu | Esc, repeated as needed |
| Controls / unit and building reference | F1 / F2 |

On a Mac whose function keys adjust brightness or volume, hold **Fn** with
the function key. The menu also offers **How to play** and **Settings**.

## Menus, reconnecting and finishing

**The online match keeps running while a menu is open.** Agree with your
friend before stepping away. Offline Continue does not restore an online
room; use **Rejoin last room** instead.

Press **F10** to open **Match menu**. Choose **Return to match** or press
**Esc** to close it. **Settings** adjusts music, sound, scrolling and
fullscreen; **How to play** opens the controls reference.

A brief connection loss triggers automatic reconnection. The match pauses
while either player is disconnected. If it does not recover, reopen Warband
on the **same computer**, choose **Multiplayer**, then **Rejoin last room ·
CODE**. Use that button for your existing seat rather than entering the code
as a new guest. Your friend should remain in the room or use their own
**Rejoin last room** button.

Return promptly: rooms expire after about **15 minutes without both players**.
Creating or joining a different room replaces the room remembered on that
computer. After reconnecting, check your units before repeating an order;
orders interrupted by the lost connection are not automatically resent.

To leave, press **F10 → Leave match**, or **Quit** to close the app. Leaving
disconnects your seat and pauses play for your friend. When a battle reaches
**Victory!** or **Defeat**, choose **Back to title**. For a rematch, create a
new room and share its new code.

## If something goes wrong

| What you see | What to do |
| --- | --- |
| **Enter a room code first.** | Copy the code your friend sent, click Paste code, then Join room. |
| **Room not found for this game. Check the room code.** | Check every character and ask your friend to confirm their current code. If the room expired, create a new one. |
| **Both seats are claimed. Reconnect using your saved seat.** | Choose Rejoin last room on the computer that previously joined. If neither of you can recover the seat, create a new room. |
| Waiting for your partner | The other seat has not connected or has disconnected. Your friend should join the current code once, or use Rejoin last room for a seat they already occupied. |
| **Cannot reach the online server** | Check that your internet connection works, cancel back to Multiplayer, and retry. If both players get it, try again later. |
| **Connection lost — reconnecting to your room…** | Give the automatic reconnect a moment; if it fails, use Rejoin last room on the same computer. |
| The worker walks instead of gathering | Select a Peasant and right-click directly on the mine or tree. Right-clicking bare ground orders movement. |
| A worker waits instead of finding a job | Stop/Hold may have parked it. Give another order, or explore a safe resource and route. Automatic work does not scout through unknown terrain. |
| A construction site has no builder | Select a Peasant and right-click the unfinished building. |
| Text is too small | Open F10 → Settings, use **+** beside **Fullscreen** to set it to **On**, then press Esc to apply it. |
| Panels overlap even in fullscreen | Send a screenshot and your display size with the report. Resizing the window scales the layout and may not fix an overlap. |
| The Mac app says damaged, or Windows reports malware | Download a fresh copy from the release linked above. If the alert persists, stop and report its exact wording. |
| Windows blocks the app with **Smart App Control**, with no Run anyway option | This unsigned preview may be blocked on that PC. [Microsoft confirms there is no per-app exception](https://support.microsoft.com/en-us/windows/security/threat-malware-protection/smart-app-control-frequently-asked-questions); report the block so a signed release can address it. |

If you need help, send the game version, Mac or Windows version, the action
you took, and the exact error or a screenshot through the
[issue tracker](https://github.com/ikamensh/saga2d/issues). Share only the room
code with your friend; game settings contain your private reconnect seat.
