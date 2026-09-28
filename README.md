# Entry-level ME job scanner

Watches the job boards of the companies in `companies.toml` and sends a Discord
message, with the apply link, as soon as a new posting appears that is:

- full-time (internships, co-ops, contract and part-time roles are skipped)
- entry level (entry-level title, or 2 or fewer years of experience required)
- located in the United States
- asking for a bachelor's degree that a Mechanical Engineering graduate holds

It runs on GitHub Actions once an hour, at 30 minutes past, so it keeps working
while your computer is off.

## One-time setup

1. **Discord webhook.** In Discord, open the channel that should receive alerts:
   Edit Channel > Integrations > Webhooks > New Webhook > Copy Webhook URL.
   Treat this URL like a password.
2. **GitHub repository.** Create a free GitHub account, then a new **public**,
   empty repository (no README), for example `job-scanner`. Public repositories
   get unlimited free Actions time.
3. **Add the secret.** In the repository: Settings > Secrets and variables >
   Actions > New repository secret. Name `DISCORD_WEBHOOK_URL`, value = the URL
   from step 1.
4. **Upload the code.** From this folder:

   ```bash
   git init -b main
   git add .
   git commit -m "Job scanner"
   git remote add origin https://github.com/YOUR-USERNAME/job-scanner.git
   git push -u origin main
   ```
5. **Start it.** In the repository: Actions > Scan job boards > Run workflow.
   The first scan takes about 5 minutes and sends one summary per company of
   the matching jobs that are already open. From then on only new postings
   alert, and scans take under a minute.

## Adding and removing companies

```bash
python add_company.py "Company Name" https://link-to-their-job-list
```

The tool works out the job system from the link, checks that the board
responds, and adds it to `companies.toml`. Then upload the change:

```bash
git add companies.toml
git commit -m "Add company"
git push
```

You can also edit `companies.toml` directly on github.com. To stop watching a
company, delete its block.

Supported job systems: Greenhouse, Lever, Ashby, Workday, SmartRecruiters,
Oracle, ClearCompany, and career sites built on Jibe (iCIMS) or Radancy.
Companies on other systems cannot be scanned yet. Known examples: Celestica,
Supermicro, Halliburton (SuccessFactors), Lockheed Martin, Eaton, Qualcomm
(Eightfold), Bell and Textron Aviation (Taleo), Tesla (blocks automated
access) and Apple (its own site).

## Tuning what alerts

All settings are in `config.toml`, each with a note explaining it. The ones
that matter most:

| Setting | Effect |
| --- | --- |
| `max_years_experience` | Highest required experience that still counts as entry level (default 2). |
| `include_unclear_level` | Alert on postings that state no experience requirement. |
| `include_general_engineering_degree` | Alert on "bachelor's in engineering or related field" postings, not only ones naming Mechanical Engineering. |
| `title_exclude_keywords` | Titles containing these words are skipped. |

Every alert states why it matched, for example
`Mechanical Engineering B.S. listed · Entry-level title`.

## Running it on your own computer

```bash
python -m scanner --dry-run --explain
```

`--dry-run` prints alerts instead of sending them. `--explain` also prints why
other candidate jobs were rejected. Add `--company "SpaceX"` to scan one
company. Tests: `python -m unittest discover -s tests`.

## How it behaves

- **Speed.** A scan starts once an hour, at 30 minutes past. GitHub sometimes
  starts scheduled runs late, so a job posted just after a scan can take a little
  over an hour to alert. To scan more often, change the `cron` line in
  `.github/workflows/scan.yml`.
- **Daily check-in.** One "scanner is running" message per day around 9 AM
  Central. If it stops arriving, look at the Actions tab.
- **Broken boards.** If a company's board fails three scans in a row, you get
  one warning message. Companies do change job systems occasionally.
- **Memory.** Seen jobs are stored on the repository's `state` branch. Deleting
  that branch makes the next scan behave like a first scan.
