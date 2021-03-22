## A premium ticket bot without the premium price.

# Features
1. Automatically close tickets if the ticket is left empty after creation.
2. Automatically close tickets if the ticket creator leaves the Discord.
3. Automatically close tickets if the ticket creator takes too long to respond.
4. HTML transcripts will be sent to your logs channel and to the ticket creator in DMs.
5. A reaction panel or commands can be used to open and close tickets.
6. Custom bot prefix.

# Setup
1. [Click here](https://discord.com/oauth2/authorize?client_id=809975422640717845&permissions=268560464&scope=bot) to invite the bot to your server.
3. Create a new `tickets` channel category. It doesn't necessarily have to be named tickets.
4. Remove `@everyone`'s viewing permissions from `tickets`.
5. Give your support team and `@BirdTickets` permission viewing permissions in the category.
6. Set the category with `-setcategory <category_id>`. You may need to [enable developer mode](https://support.discord.com/hc/en-us/articles/206346498-Where-can-I-find-my-User-Server-Message-ID-) to get the category ID.
7. (Optional) Use the `-panel` command wherever you want the panel to be.
8. (Optional) Create a transcript channel with `-setlog <channel_mention>`.
9. (Optional) Change the prefix with `-setprefix <new_prefix>`.

# Support
If you run into any issues or bugs, you can ask for help in the [Birdflop Hosting Discord](https://discord.gg/ZrRvTMu).
