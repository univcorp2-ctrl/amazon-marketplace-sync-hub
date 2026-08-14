# Shopee blacklist research baseline

Updated: 2026-08-14

This repository uses a conservative automation policy. It is intentionally stricter than a single marketplace policy. A `deny` match is never auto-listed. A `review` match is also blocked while `SHOPEE_POLICY_STRICT=true`. Destination-market law and current Shopee policy remain authoritative.

## Official Shopee sources checked

- Singapore: What are Prohibited Listings? — https://seller.shopee.sg/edu/article/36
- Singapore: Shopee listing policy — https://seller.shopee.sg/edu/article/18461/listing-policy
- Singapore: Guidelines on medications, health supplements, and drugs — https://seller.shopee.sg/edu/article/7203
- Singapore: Sale of E-vaporisers and other Imitation Tobacco Products — https://seller.shopee.sg/edu/article/20354
- Singapore: Regulations on Selling Guns, Explosive Precursors, Weapons and Noxious Substances — https://seller.shopee.sg/edu/article/26932
- Singapore: Shopee Direct Programmes — https://seller.shopee.sg/edu/article/26946
- Philippines: List of Prohibited and Restricted Items — https://seller.shopee.ph/edu/article/698
- Philippines: Prohibited Products in the Shopee International Platform — https://seller.shopee.ph/edu/article/19349
- Philippines: Prohibited Food Related Items Listing Policy — https://seller.shopee.ph/edu/article/25065
- Philippines: Listing Violations — https://seller.shopee.ph/edu/article/24949

## Automatic deny baseline

The deny baseline covers firearms, weapons, ammunition, explosive materials and precursors; illegal and controlled recreational drugs and paraphernalia; tobacco, nicotine, vaping and imitation tobacco; counterfeit and piracy signals; endangered wildlife and wildlife-derived products; live animals and human remains; stolen or illicit fraud/security goods; explicit pornographic goods; forged identity/government documents; illicit financial instruments; and clearly prohibited services/accounts.

## Strict review baseline

The review baseline covers alcohol; medicines; medical devices and diagnostics; supplements and health claims; contact lenses; cosmetics with regulated claims; food and ingestibles; hazardous chemicals and pesticides; lithium batteries, power banks and strong magnets; liquids, aerosols, pressurised/flammable goods; plants, seeds and soil; large/bulky goods; covert surveillance and jamming devices; radio and laser products; gambling, lottery and randomised sales; precious metals/currency; baby safety products; pet food and veterinary products; automotive safety parts; mains/high-power electrical goods; religious/political sensitive goods; high-risk branded goods; digital goods/accounts/codes; personal-data/security credentials; sexual/fertility health goods; high-risk industrial tools; and suspicious medical/regulatory claims.

## Market additions

Market-specific blocks are additive. Singapore adds strong blocks for tobacco/vaping, wildlife, weapons/explosive precursor terms, plus cross-border logistics review for lithium batteries and large liquids. Philippines adds explicit blocks for contact lenses, adult toys, counterfeit/inspired items and selected cross-border categories such as live animals/plants and bulky goods. Other supported markets retain the conservative global baseline and an additional regulated-goods review layer until a market-specific rule has been verified.

## Safe starting presets

`data/automation_presets.json` contains 15 low-risk starting searches. Presets are not a whitelist: every candidate must still pass blacklist, availability, price, duplicate, content-rights and destination-market gates.
