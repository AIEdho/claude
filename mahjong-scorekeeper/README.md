# HK Mahjong Scorekeeper

A single-file, no-install web app for tracking chips in a Hong Kong style mahjong game.

## Use it

Just open `index.html` in a browser (double-click it, or serve the folder with any static file server). Works great on a phone at the table. All state is saved to the browser's local storage, so refreshing or closing the tab won't lose your game.

## What it does

- Enter 4 player names and a starting chip count (default $2000).
- After each hand, record the round: winner, fan count, and whether it was a self-draw or a win off someone's discard (and who discarded).
- Record kongs (4-of-a-kind melds) separately, any time they happen — exposed kong costs $1/player, concealed (self-drawn) kong costs $2/player, paid to whoever made the kong. Multiple kongs can be logged in the same round.
- Balances, net totals, and a full round-by-round history update automatically.
- "Undo Last" reverts the most recent round if you mis-entered something.

## Scoring rules (defaults, all editable in Settings)

- **Fan value**: base unit ($2 default) doubles for every fan starting at 3 fan (e.g. 3 fan = $2, 4 fan = $4, 5 fan = $8...), capped at a max fan (default 10, i.e. $256). Fan counts below 3 are treated as 3 fan (minimum winning hand).
- **Self-draw**: the other three players each pay the winner the full fan value.
- **Discard win**: the discarder pays double the fan value, the other two players each pay half — so the winner always collects the same total (3x the fan value) either way. (This split rule is the default; "discarder pays it all alone" is also available in Settings.)
- **Kong payments**: independent of who wins the hand. Exposed kong = $1/player (default), concealed/self-drawn kong = $2/player (default) — both configurable.

## New Game

"New Game" wipes the current scoreboard and history and takes you back to setup. There's a confirmation prompt so you don't lose an in-progress game by accident.
