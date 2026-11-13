# EPG auto-assign: short user guide

The panel can now link EPG to your live channels by itself, using the EPG providers you already added under EPGs (any number of them). Nothing runs outside the panel and nothing is fetched from anywhere else.

## How it decides

- It only fills channels that have no working EPG link. A channel that already has one (picked by hand or assigned earlier) is never changed.
- It only links when it is sure: the cleaned-up channel name (without `UK:`, `|UK|`, `HD`, `FHD`, `4K` and similar) matches exactly one provider channel. `+1` channels only match `+1` channels. "BBC One" never gets "BBC One London" by guessing, and a name that exists in two countries is left alone unless the channel name or category says which country.
- If two providers both have the channel, the one higher in the priority list wins.
- Everything it is not sure about stays unassigned and is listed for you to review. It never guesses.
- Channels in categories you exclude (cameras, CCTV, private) are never touched.

## Where it is

Management, then Service Setups, then EPGs. The new card **Auto-assign EPG** sits above the list of providers.

| Control | What it does |
|---|---|
| Auto-assign EPG On/Off | When On, every EPG update (the scheduled one and **Force EPG Reload**) first refreshes the providers, then assigns, then downloads programmes for the newly linked channels in the same run. Default is Off. |
| Provider priority | Order used when more than one provider has the same channel. Use Up/Down. The number shows how many channels with programmes the provider had at the last run. |
| Excluded categories | Select the categories that must never be auto-assigned. Red names look like camera or private categories. Always exclude them: linked channels are published in the XMLTV file to every viewer. |
| Max changes per run | Safety cap (default 5,000). What is left over is picked up by the next run. |
| Include radio | Also assign radio channels. |
| Save settings | Stores the form. Preview and Assign now stay disabled until you save ("Save settings first"). |
| Preview | Dry run. Shows what would be assigned and changes nothing. |
| Also re-assign dead links automatically | Off by default. When On, the update and Assign now also move channels whose provider channel has disappeared (see "Dead links" below). |
| Assign now | Runs the assignment in the background right now (no download). The card shows the progress and then the result. |
| Dead link: re-assign after this many runs | Default 3. A dead link is only re-assigned after its channel has been missing from the provider in this many EPG updates in a row (see "Dead links"). 1 to 10. |
| Preferred EPG language | Empty (default): the first language the provider offers for the channel, as before. Type a code such as `en` to pick that language when the provider offers it (`en` also takes `en-US`); channels that do not offer it keep the first language. |
| Re-assign dead links now | One-off run that also re-assigns dead links (only those that have been missing long enough), whatever the setting says. Asks for confirmation first. |
| Opted out (cleared by hand) / Release all | Shows how many channels you cleared by hand. Auto-assign skips them. **Release all** puts them back into the normal pool. |
| Channels in excluded categories that still have an EPG link / Clear EPG for these | Warning with a count. These links are published in the EPG feed to all viewers. The button clears them after a confirmation. It is never done automatically and can be undone. |
| Accept current size | Appears on a provider that the 30% shrink guard is holding back. Use it when the smaller list is really correct (see "Dead links"). |
| Download report (CSV) | Channels it did not assign: ambiguous, unmatched, deferred, dead links (status `dead_link`, with the old link, how many runs it was missing and the best candidates), would-assign after a Preview, channels you cleared by hand (`opted_out`) and linked channels in excluded categories (`excluded_linked`). |
| Review ambiguous | Lists the ambiguous channels and the dead links with their candidates. **Assign** next to a candidate links it. |

## Recommended first run

1. Add your providers and press **Force EPG Reload** once so every provider has its channel list.
2. Tick the camera/CCTV/private categories under **Excluded categories** and press **Save settings**.
3. Press **Preview**, read the numbers, download the report and look at **Review ambiguous**.
4. Press **Assign now**. Programmes appear after the next EPG update, or press **Force EPG Reload** to get them now.
5. Switch **Auto-assign EPG** to On and Save. From then on new channels and new providers are handled automatically.

Linking thousands of channels makes the EPG update store many more programmes (per channel, for the days you keep). Expect the first update after a big assignment to take longer and the database to grow. That is why the toggle starts Off and the cap exists.

## Providers are dynamic: adding and deleting

Nothing depends on the five providers you have today. The provider list is read from the EPGs page on every run, so you can add or delete providers at any time. The priority list keeps your order for the providers that still exist; a provider you add later goes to the end of the list (move it up if you want it to win).

**Adding a provider.** Add it under EPGs as usual and press **Force EPG Reload**. The update reads the new provider, auto-assign fills the channels that were still unassigned, and programmes are downloaded for them in the same run. Channels the new provider does not have stay unassigned.

**Deleting a provider.** Delete it under EPGs as usual (the confirmation reminds you of the next point).
- The provider's stored programmes are removed with it. Programmes of providers that were deleted before this version are cleaned up by the next EPG update or Assign now. Programmes of providers that still exist are never touched.
- Channels that were linked to the deleted provider are treated like unassigned channels when Auto-assign is On. The next run (the next EPG update, Force EPG Reload or Assign now) gives each of them the best match from the providers that are left, using the same rules and priority as before, and overwrites the dead link. A channel is only moved when the match is certain; the others stay listed as unmatched or ambiguous so you can pick one by hand.
- The result card shows "Re-assigned after provider deleted: X / Y" (X moved, Y found). The Streams list filter **No EPG** lists these channels too.
- In the channel editor (EPG tab) the box **Assigned EPG** says "provider deleted - will be re-assigned automatically when Auto-assign is On, or pick one below" (with Auto-assign Off nothing is re-assigned until you pick a channel or turn it On). The old link stays selected, so saving the channel does not change it by accident.
- Add the replacement provider and press Force EPG Reload and the remaining channels are filled from it.

## Dead links: the provider is still there but the channel is gone

Sometimes a provider keeps existing but drops a channel (renamed, removed from its list). The channel then stays linked and shows no programmes.

- Auto-assign finds these **dead links** on every run: the channel is linked to an existing provider, that provider's channel list is valid, and the channel id is no longer in it. The count is on the result card ("Dead links: N"), they are in the CSV report (status `dead_link`, with what the channel used to be linked to and the best candidates) and in **Review ambiguous** (marked "Dead link").
- By default nothing is changed. A provider file can be broken or partial for a day, and that must not rewrite links you chose by hand. In the editor the box says "channel no longer in this provider".
- A dead link is only re-assigned after its channel has been missing in **3 EPG updates in a row** (changeable on the card). Only the scheduled EPG update counts; pressing Preview or Assign now does not move the counter, and a channel that comes back resets it. The report shows "missing in N runs" and the review list shows "N/3 runs". While a counter is running the daily update is not skipped even if nothing else changed.
- To fix them, either press **Assign** in the review list for each channel, set **Also re-assign dead links automatically** to On, or press **Re-assign dead links now** once. Only a certain match is used; the rest stay listed. The dead link is overwritten (provider, channel and language).
- Safety guard: a provider is skipped for dead links when its channel list is empty or invalid, or when it lost more than 30% of its channels with programmes since the previous run (a sign of a partial file). The card names the provider and the reason ("Dead-link check skipped: Name (shrunk)"). While a provider stays that small the guard stays on (its previous channel count is kept); fix or reload the provider, press **Accept current size** next to it on the card if the smaller list is really the new normal, or use **Assign** in the review list for single channels. Channels in an excluded category are never treated as dead links.

## Fixing a wrong or missing match

Open the channel (Streams, edit) and go to the **EPG** tab:

- **Assigned EPG** shows what the channel uses now (provider, channel, how many programmes are stored).
- **Quick Search** searches the channel lists of all providers (type at least 2 letters). Click a result and the EPG source, channel and language fields are filled. Press the normal **Edit** button to save. A channel you saved by hand is never overwritten by auto-assign. A result with "0 programmes" has no guide data in the provider file and asks for confirmation.
- **Suggested** shows the best candidates for this channel's name.
- **Clear EPG** empties the three fields. When Auto-assign is On, a channel you cleared and saved is remembered ("opted out") and auto-assign leaves it empty. It comes back into the pool when you pick an EPG for it by hand or press **Release all** on the card. When Auto-assign is Off nothing is remembered (the channel can be assigned if you switch it On later; put its category in the excluded list to keep it empty for good).
- The old per-provider dropdowns still work as before.

A channel whose EPG link points to a provider channel that has since disappeared is a dead link (see above): it is reported, and not changed unless you ask for it. A channel linked to a provider that was deleted is re-assigned automatically.

## Mass actions

- Streams list and mass edit have a **No EPG** filter that lists exactly the channels auto-assign would fill.
- Mass edit has **Clear EPG** (details tab): tick it, select the channels and save. With Auto-assign On they are remembered as opted out, like the Clear button in the editor. The last tab has **Restart on edit** ticked by default (that is how the page always worked); untick it if you only want to clear EPG without restarting the streams.

## Notes

- "Eligible" now means: no link, a link without a channel, or a link to a provider that no longer exists. Preview, Assign now, the update, the **No EPG** filter and the skip check all use the same rule.
- Channels that were saved with "No EPG" earlier can still hold an old channel id in the database. Those count as unassigned and the old id is overwritten when a match is found.
- A run never overlaps with another one. If you press Assign now while the EPG update is running, it says another run is active.
- Where things are kept: the settings and the last run summary in the panel's existing settings table, reports and logs in `logs/epg_auto/` (`epg_auto.log`, `report_latest.csv`, `changes_<time>.tsv`). The last 10 `changes_*.tsv` files are kept, and the command `php tools/epg_assign.php --undo=logs/epg_auto/changes_<time>.tsv` reverts a run's links (only channels that still hold the values that run wrote).
- To turn the feature off completely, switch the toggle Off. Nothing changes in how the EPG update works while it is Off.
## What changed in the EPG update itself
These changes keep the stored programmes exactly the same; they only make the update faster and tidier.
- The update now writes programmes in batches (500 at a time, one transaction per provider) instead of one by one. If a batch is refused by the database, it is repeated row by row, so a single bad programme is skipped like before.
- The clean-up of duplicate programmes at the end of the update uses a faster statement. It keeps the newest copy of each programme, as before.
- Importing an M3U with tvg-id values no longer decodes all provider data again for every line, so big imports finish much sooner. The channel found for each tvg-id is the same as before.
- Leftover temporary files of the channel search index (`logs/epg_auto/index.cache.<number>.tmp`, left behind only if a run was killed) are removed automatically once they are older than one hour.
- The confirmation text on the EPGs page and the EPG tab only promise re-assignment "when Auto-assign is On".

## Limits and recommendations
**Days to keep.** Each linked channel stores every programme for the days you keep. Plan for roughly 280 programmes per channel for 7 days. At 12,000 linked channels that is about 3.4 million rows, which needs about 2 to 4 GB of database space (more while an update is running). If disk or RAM is tight, set **Days to Keep** to 2 or 3 on the providers (EPGs page, Edit) instead of 7. Keep at least 2 so that "today" and "tomorrow" are always available in the apps. Lowering it frees space at the next update. Backups skip the programme table.
**Expected update time (cron).** The update is the existing EPG cron (`crons/epg.php`); ask your host for its schedule with `crontab -u xtreamcodes -l`. Time depends on the server, the provider file sizes and the number of linked channels. In the test setup, one run for 12,000 linked channels was measured at about 24 seconds for the inserts (it used to be about 167 seconds) plus the duplicate clean-up; a production server with disk sync and network delay will be slower. Before relying on it, time one run on your server (`time sudo -u xtreamcodes php /home/xtreamcodes/iptv_xtream_codes/crons/epg.php`) and make sure the schedule is longer than that. A new update stops an older one that is still running. Run **Assign now** or **Force EPG Reload** outside busy hours: the first run after a big assignment is the longest.
**When the guide is wrong for a channel.** Open the channel (Streams, Edit, EPG tab), choose another source with Quick Search or the Suggested list, pick the channel and save; or press **Clear EPG** and save to remove the link. A link you set by hand is never overwritten by auto-assign. If you clear it, the channel becomes eligible again at the next run; to keep it empty, put its category in **Excluded categories**. Use the Review list on the EPGs page for many at once (Assign per row). The **Undo** command (`php tools/epg_assign.php --undo=...`) reverts a whole run.
**Excluded categories for private channels.** Tick every camera, CCTV, private or customer-only category under **Excluded categories** before the first run. Auto-assign never changes channels in those categories (new links or dead-link fixes). Channels that already carry an EPG link keep it, and the XMLTV file lists every stream that has one, so do not assign EPG to private channels, and clear any link a private channel already has. If you move a channel into an excluded category later, its existing link stays; press **Clear EPG** for it.

## What changed in the EPG update (decisions round)
- **Only the difference is written.** The update no longer inserts every programme again each day. For each linked channel it compares what is stored with what the provider sends from the first programme in the feed onward: unchanged programmes stay, corrected, moved or removed ones are replaced or deleted, new ones are added. Rows older than the first programme in the feed are left until the days to keep run out. If a provider is down or sends an empty file, its stored programmes are left alone. The table no longer grows when nothing changed, and the database no longer burns through ids.
- **Force EPG Reload no longer empties the programme table first.** It runs the same update. The result for every linked channel is the same as after the old empty-and-reload. Programmes of providers that no channel uses stay until Auto-assign's clean-up removes them (see below) or the days to keep run out.
- **Clean-up of unused providers (Auto-assign On only).** After each update, programmes of providers that no channel uses any more are deleted, at most 200,000 rows per update; the next update continues. Providers you delete are cleaned as before.
- **Titles in the right language, and a fallback.** If a channel's EPG language is not found in a programme, the first title the provider sent is used instead of leaving the title empty. A channel with no language (empty, or the old text "NULL") uses a title without language, or the first title.
- **Safer matching.** A channel with a country in its name or category (`UK:`, `US|`, category "Canada", "Arabic") is never linked to a provider channel of a different country. A channel without a country is not linked when the same name exists in several countries ("Discovery"). Very short or very general names (under 4 letters, or only words like "One", "News", "Sports", "Movies") are only linked when the country matches, or when the provider's channel id is spelled exactly like the channel name; otherwise they appear in the review list.
- **Database change (once, automatic).** The programme table gets a faster index and its id column becomes BIGINT. The EPG update does this by itself the first time it runs after the upgrade (a few seconds for about 80,000 rows, the panel keeps working) and never again. Fresh installs already have it. The exact manual commands are in "Upgrade and migration" below. Programme data is not changed. Backups still skip this table.

## Adding more countries
1. Add the EPG provider for the country under EPGs (Source URL) and press **Force EPG Reload**.
2. Make sure the channels say which country they belong to. Either put the country in the channel name (`UK: BBC One`, `|CA| Global`) or keep the channels in a category whose name contains the country (`UK`, `Canada`, `India`, `Arabic`). Without it, names that exist in several countries (Discovery, Sky News, ESPN) are left for the review list instead of being guessed.
3. Move the new provider in the priority list if it should win over another provider for the same channel.
4. Press **Preview**, then **Assign now**. Channels the new provider does not cover stay unassigned and are picked up the next time you add a provider.
5. For languages other than the provider's first one, type the language code under **Preferred EPG language** (for example `en`).

## Accuracy update

The matcher was rebuilt after a test on a real list of about 12,600 live channels and two large EPG providers. Before, only a few hundred channels were linked and about 1 in 4 of those was wrong. Now about 3,000 are linked and 139 of 140 spot-checked links were right. The spot-check set is the one the rules were tuned on, so treat that as a best case.

### How matching works now

- **Provider tags are cleaned.** Providers add their own tags to names and ids, such as a trailing ` US`, or `.us2` and `.us_locals1` at the end of an id. These are read as country tags and removed, so both sides can be compared.
- **US and Canadian local stations are matched by call sign.** The call sign is the four letters starting with K or W (for example WSVN or KTAZ), or the Canadian C-call signs. Keep it in the channel name, like `FL | Miami | FOX WSVN`. If the name says CBS but the call sign belongs to an NBC station, the channel goes to Review.
- **Country prefixes are understood:** `USA`, `US`, `CA`, `PT`, `BR`, `LA` (Latin America) and `CARIB` (Caribbean), next to the ones that already worked (`UK:`, `|UK|` and so on).
- **US state codes are states, not countries.** `CA | Los Angeles | CBS 9 KCAL` is California, `IN | Indianapolis | NBC WTHR` is Indiana. They are no longer read as Canada or India.
- **Names without a country use the home country.** A name that exists in several countries (CNN, Discovery, TCM) and has no country in the name or category is linked to the home country copy. The home country is `us` unless you change it. If the category is too general to say (for example Latin America), the channel goes to Review.

### The numbers on the card

The card says, in plain English, for example: Assigned 3,023, Needs review 752, No match in your providers 2,959, Not EPG-able 5,917.

| Number | Meaning | What you do |
|---|---|---|
| Assigned | Confident matches only: call sign, an exact name in the right country, or league and team. Written automatically. | Nothing. Fix a single wrong one in the channel's EPG tab. |
| Needs review | A candidate exists but the engine will not guess. Each one has a reason. | Open **Review ambiguous** and press **Assign** next to the right candidate. |
| No match in your providers | None of your providers has this channel. | Add a provider that carries it and press **Force EPG Reload**. |
| Not EPG-able | Channels that cannot have a normal TV guide (see below). Never linked. | Nothing. |

The old technical line (Ambiguous, Unmatched, Deferred, excluded, dead links) stays below for reference.

The CSV report has two extra columns, `reason` and `reason_text`, for every channel. Statuses are `ambiguous`, `unmatched` and `not_epgable`; existing links that look wrong are listed as `link_suspect` (counted and reported only, never changed). The Review list has the same reasons in plain words, with filters by category and reason.

If a run found confident matches but wrote none (database errors, or channels that were no longer fillable), the card says so and why. A zero is never silent.

### Not EPG-able

These channels are left alone on purpose and are never linked, not even by hand from Review:

- 24/7 loops (a channel that plays one show or movie set all day)
- event and game slots (for example `NCAAF 73: NO EVENT`, `ESPN+ 155 | A vs. B`)
- pay-per-view slots
- adult channels
- cameras
- channels with a blank name

If a class is wrong for you (for example a real 24/7 news channel), switch it off under Advanced matching with **Treat as normal list**.

### New settings (card, Advanced matching)

| Setting | What it does |
|---|---|
| Home country | Country used for names that have no country. Default `us`. Change it if most of your channels are from somewhere else. |
| Country tags (`word=cc`) | Your own prefixes, one per line, for example `sp=mx`. Use `word=!` to remove a built-in tag. |
| Category hints (`word=cc`) | A word in a category name that tells the country, for example `portugal=pt`. Special values: `latam` (Latin America), `carib` (Caribbean), `asia`, and `-` (no country, do not guess). |
| Not EPG-able categories | Categories whose channels are all treated as Not EPG-able (for example a category of event slots). |
| Treat as normal list | Not EPG-able classes you want treated as normal channels. |
| Suggested categories button | After a run the card can suggest categories that look like event or 24/7 lists. One click adds them to the Not EPG-able list. |
| Caribbean may use the US copy | Whether Caribbean channels may use the US version of a US network. |

One-click accept for a whole category is built (**Preview and accept suggestions**: a list with checkboxes, a count, and a confirmation before anything is written; it can be undone with the Undo command). It is switched off for now because no review reason has been measured as safe enough. Use **Assign** per row in Review.

### Naming tips

- Keep live channels in country-named categories, for example `USA`, `UK Sports`, `Canada`, `Portugal`. The category is used as the country hint.
- If a category name has no country word (for example `CABLE`, `NEWS`, `LOCAL - NBC`), add a Category hint such as `cable=us`.
- Put the country prefix in channel names where you can (`PT | SIC`, `CA | TSN 3`).
- Keep the call sign in names of local stations.
- Use separate categories for 24/7 loops and for event slots. Then they are easy to put under Not EPG-able categories.

### Works with any providers and channels

Nothing is tied to specific providers or channel lists. Providers can be added or deleted at any time. If your panel is not US-based, set the Home country and review the built-in tag and category lists before the first run. Always press **Preview** and spot-check a few channels before **Assign now**.

## Upgrade and migration

**Automatic, once only.** The first time `crons/epg.php` runs on the new build, it changes the `epg_data` table (only that table):

- adds the index `epg_chan_start` on `(epg_id, channel_id, start)`
- changes `id` from INT to BIGINT

It checks the table first and does nothing if both are already in place, so it never errors and never repeats. If you restore an old dump later, the next cron run applies it again. Each ALTER is logged with its duration in `logs/epg_migrate.log` (nothing is written when there is nothing to do). Measured on about 80,000 rows: about 1 second in total, and the panel keeps working (readers are not blocked). If a long query holds a lock on the table, the cron gives up after 5 seconds, carries on, and tries again the next day. Tables estimated above 20 million rows are skipped with a log line; run the SQL below by hand then. Programme data is not changed and the old single-column indexes stay. Fresh installs already have the new layout in `database.sql`.

**Manual SQL** (same result; run in this order in the `mysql` client against the panel database):

```sql
ALTER TABLE `epg_data` ADD INDEX `epg_chan_start` (`epg_id`,`channel_id`,`start`), ALGORITHM=INPLACE, LOCK=NONE;
ALTER TABLE `epg_data` MODIFY `id` BIGINT(20) NOT NULL AUTO_INCREMENT, ALGORITHM=COPY, LOCK=SHARED;
```

**Dump and restore compatibility** (tested on MySQL 8.0 and MariaDB):

| Case | Result |
|---|---|
| Old panel full dump restored into the new panel | Loads without error, rows identical. The old INT format comes back and the next cron run migrates it again. |
| Old rows-only dump into the new panel | Loads, identical. |
| Rows copied with ids +1,000,000 into the new BIGINT table | Loads, nothing lost, AUTO_INCREMENT stays above the highest id. |
| New panel full dump restored into an old-format panel | Loads, and the old cron runs against it without error. |
| New rows-only dump into an old INT table | Loads (ids are far below the INT limit). |
| New dump into the new panel | Loads, migration does nothing. |
| MySQL dumps into MariaDB and the reverse (`epg_data`) | Loads. |
| Panel Backup / Restore | Excludes `epg_data`, as before. After a restore, the next EPG update or **Force EPG Reload** rebuilds the programmes. |

The database has no foreign keys. Nothing in the panel code reads `epg_data.id`.
