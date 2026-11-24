# Coop Schweiz for Home Assistant (unofficial)

[Deutsche Fassung](README.de.md)

Syncs the shopping list of the Swiss **Coop app** ("Einkaufszettel", the list
that also shows up on the Passabene self-scanner) with a to-do list in Home
Assistant, in both directions.

> **Unofficial.** This project is not affiliated with, endorsed by or supported
> by Coop Genossenschaft. "Coop" and "Supercard" are trademarks of their
> owners. The integration talks to the same backend as the Coop app, using an
> interface that is not public. It can stop working at any time. Use it at
> your own risk, privately and only with your own account. The terms of the
> Coop services (Supercard, digital shopping list, coop.ch; read in November
> 2026) do not mention third-party programs, but they limit the services to
> private, non-commercial use and allow Coop to exclude accounts at its own
> discretion.
> If Coop wants this project changed or removed, please open an issue; that
> will be respected.

## Status

Early version (0.x). Developed and tested by one person on one account.

## What it does

- One to-do list entity per Coop shopping list.
- Add, check, uncheck, rename and delete products from Home Assistant
  (dashboard, automations, voice assistants).
- Changes made in the Coop app appear in Home Assistant after at most
  5 minutes (polling).
- Quantities: `2x Milch` adds two of "Milch"; the list shows `2× Milch`.
- **Products from the Coop catalogue:** the included dashboard card suggests
  products from the whole Coop range while you type. Products added this
  way carry the Coop product number, so the Coop app and the Passabene
  self-scanner know exactly which product is meant.
- **No duplicates:** adding a name that is already known (on the list,
  checked off, or in the app's history) re-uses that product instead of
  creating a second, free-text entry.

## Requirements

- Home Assistant 2024.11 or newer
- A Supercard ID with at least one shopping list in the Coop app
- A computer with a browser for the one-time sign-in

## Installation

### HACS (custom repository)

1. HACS → menu → *Custom repositories*
2. Repository `https://github.com/Lokutos/ha-coop-schweiz`, type *Integration*
3. Search for "Coop Schweiz" in HACS, open it and choose *Download*, then restart Home Assistant

### Manual

Copy `custom_components/coop_schweiz` into the `custom_components`
folder of your Home Assistant configuration and restart.

## Setup

1. *Settings → Devices & services → Add integration → Coop Schweiz*
2. Open the sign-in link from the dialog **on a computer** (on a phone the
   Coop app takes over the sign-in) and sign in with your Supercard ID.
3. You land on an error page. That is expected. Copy the **full address**
   from the address bar (it contains `code=`) and paste it into the dialog
   **right away**: the code is only valid for a short time.
4. Choose the list.

Add the integration again for further lists.

## Dashboard card

The integration ships its own card; nothing has to be installed
separately. Add a *Manual* card to a dashboard:

```yaml
type: custom:coop-schweiz-card
entity: todo.coop_schweiz_einkaufszettel
```

Type at least two letters to get suggestions from the Coop catalogue.
Choose one to add that product, or press Enter to add your text as it is.
Every open product shows its quantity with − and + buttons.
Options: `title` (heading) and `show_completed: false` (hide checked
products). If the card is unknown right after installing, reload the
browser page once.

## Action `coop_schweiz.add_product`

Adds a catalogue product by its Coop product number, for automations and
scripts:

```yaml
action: coop_schweiz.add_product
target:
  entity_id: todo.coop_schweiz_einkaufszettel
data:
  code: "6554381"
  quantity: 2
```

## Known limitations

- Polling every 5 minutes; no push updates.
- Products from the Coop catalogue can not be renamed from Home Assistant,
  only their quantity can be changed.
- Text added without choosing a suggestion (for example by voice) becomes a
  free-text product, unless a product of exactly that name is already known.
- The product search uses the catalogue of the Coop app; suggestions need an
  internet connection and are cached for 10 minutes.
- A product name that itself starts with a number and "x" (for example
  `6 x Eier`) is read as a quantity when you add it in Home Assistant.
- The sign-in page is in German. Product names are shown in the language of
  Home Assistant if the list has them (German, French, Italian, English).
- If the list is deleted in the Coop app, remove the entry and set it up
  again.

## Privacy and security

- The integration only talks to servers of Coop (`login.supercard.ch`,
  `www.coop.ch`) and to Google Firebase, where Coop stores the list. Nothing
  is sent anywhere else. What you type into the card's field (two characters
  or more) is sent to `www.coop.ch` as a search term, without your account.
  Product pictures in the card are loaded by your browser directly from
  `www.coop.ch`.
- Your password is never seen by Home Assistant. The sign-in yields a
  **refresh token**, which is stored in the config entry. Home Assistant
  keeps config entries **unencrypted** in `.storage`, so the token is also
  part of your backups. Whoever has the token can act as you towards the Coop
  services. Do not share backups or the `.storage` folder.
- To revoke access: remove the integration and change the password of your
  Supercard ID.
- Log messages and diagnostics of this integration contain no tokens, user
  ids, list ids or product names. Still, check logs before posting them.
  **Never post the address containing `code=`.**

## Troubleshooting

| Symptom | What to do |
|---|---|
| "The sign-in was rejected or the code has expired" | Open the link again and paste the address immediately. |
| Home Assistant asks to sign in again | The refresh token is no longer valid (for example after a password change). Follow the dialog. |
| List is "unavailable" | The Coop servers do not answer as expected; the integration retries with growing pauses (up to 1 hour). See the log. |

## Support

A private spare-time project without any promise of support. Bug reports are
welcome as GitHub issues. How the interface works is described in
[docs/protocol.md](docs/protocol.md).

## License

[MIT](LICENSE). The license covers the code of this project, not the fixed
values of the Coop app contained in `const.py`.
