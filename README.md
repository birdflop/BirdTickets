## Premium tickets without the premium price.

# Features
1. Automatically close tickets if the ticket is left empty 30 minutes after creation (will warn after 15m).
2. Automatically close tickets if the ticket creator leaves the Discord.
3. Automatically close tickets if the creator fails to respond for 48 hours (will warn after 24h).
4. HTML transcripts will be sent to your logs channel and to the ticket owner in PMs.
5. A reaction panel or commands can be used to open and close tickets.
7. Custom bot prefix.
8. Add and remove people from tickets.

# Setup
1. [Click here](https://discord.com/oauth2/authorize?client_id=809975422640717845&permissions=268560464&scope=bot) to invite the bot to your server.
2. Create a new private category.

   <img src="https://i.imgur.com/JuEkppE.png">
3. Add `@BirdTickets` and your support team to the category.
   
   <img src="https://i.imgur.com/wZiE2KR.png">
4. Set the category with `-setcategory <ticket_category_id>`. You may need to enable developer mode to get the category ID.
5. (Optional) Use the `-panel` command wherever you want the panel to be.
6. (Optional) Create a transcript channel with `-setlog <channel_mention>`.
7. (Optional) Change the prefix with `-setprefix <new_prefix>`.

# Support
If you run into any issues or bugs, you can ask for help in the [Birdflop Hosting Discord](https://discord.gg/ZrRvTMu).
