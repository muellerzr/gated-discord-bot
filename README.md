# gated-discord-bot
Creating a gated course discord for Maven courses

The general idea behind this bot is so that you can both protect your content, and have an organized approach to keeping a course cohort in a discord while also simultaneously knowing who everyone is (relative to Maven).

## The Parts:

### Server

First, create a message in a **public discord channel** called "Welcome", with a singular reaction with the "+" emoji. Mine states:

```
Welcome to the Discord and Scratch to Scale!

This is the class discord, where all information relative to the class will be shared. To access this content, I require that you provide me the email you signed up for the course with, and you will be granted a @verified role.

Please respond with a ➕ emoji to this message and a bot will ask you in your DMs to provide me with the email. Once you have been verified, the rest of the discord will be made available to you.

Once again, welcome, and I hope you enjoy the class!
```


Then create a discord role called "Verified". **Whenever you make a channel, category, or more, make sure it is Private and set to only be shown to Verified people.


**Critically important**: make sure the welcome channel is *not visible* to the Verified role. This way you only see students who have not followed the verification process. 

Finally, run the server 24/7 in a screen session by running `python student_verification_bot.py`

Now when a student reacts with a +, a bot will ask them for their email associated with it.


### Auto-verify students

The second part of this process is to run `verify_students.py` which verifies students automatically. Essentially part 1 creates a database mapping student email -> discord username. This part 2 will then check that database, and if all looks well, provide the student access.

**At this time there is no automatic notice for if students aren't part of the database (ran out of time before my cohort), so just keep an eye on the welcome channel and @ everyone so they know**. 

**TO GET THE EMAIL LIST, PLEASE DM MAVEN AND MENTION THIS BOT. THEY WILL KNOW WHAT TO DO**. This endpoint will need to go into verify_students.py (see the file for the right location in its documentation).

And that's it! I've run this for the last 3 weeks as part of my cohort where it verified nearly 300 students. 
