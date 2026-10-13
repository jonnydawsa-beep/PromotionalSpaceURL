DEAL BURROW — GITHUB PAGES DEPLOY
=================================================

WHAT THIS BUILD IS
------------------
A real public comparison-site front end that is ready to consume an automated `deals.json` feed.
It does NOT invent products or savings when the miner has no validated public deals.

FILES TO PUBLISH
----------------
index.html
retailers.html
methodology.html
about.html
affiliate-disclosure.html
privacy.html
404.html
styles.css
app.js
deals.json
robots.txt
sitemap.xml
README.md

FIRST DEPLOY WITH GITHUB DESKTOP
--------------------------------
1. Clone jonnydawsa-beep/PromotionalSpaceURL in GitHub Desktop.
2. Copy the files from this build into the cloned repository folder, replacing the old site files.
3. IMPORTANT: do NOT copy the miner database, secrets.json, API tokens, raw feeds, logs or .venv into the public repo.
4. GitHub Desktop should show the changed/new files.
5. Summary: Website v1 validated-deals frontend
6. Commit to main.
7. Push origin.
8. Wait for GitHub Pages deployment, then open:
   https://jonnydawsa-beep.github.io/PromotionalSpaceURL/

CURRENT DEAL FEED
-----------------
`deals.json` is generated from publication-approved, live-revalidated signals and may contain zero or more live deals.

PUBLICATION AUTOMATION
----------------------
Product Opportunity Miner writes ONLY publication-approved, live-revalidated offers to deals.json. Do not publish raw screening candidates automatically.
