# XCape - Help people find a place to move

## Overview

Many people in France and elsewhere are concerned about the future, either for political, economic, or social reasons.   They are looking for a new place to live - in Europe or elsewhere in the world.   They each have their own criteria for choosing their new home (country, region, city) - and this application will help them identify their ideal choice.

## User Experience

The application will start by asking a few general questions about what they are looking for and why are they are leaving, to help identify a shorter list of possible targets.   So we need to find out a bit about the user:  Single, couple, family; why they are looking to leave (to avoid going to a place with similar issues), economic imperatives, medical imperatives, desiderata that most people have in mind when they start a search - cost of living, climate, urbain environment, culture, language, rental vs buy, and so on.

Once we have established the baseline, we can start narrowing down the choice among all the countries and cities in the world.   This can be done by using web search and AI to narrow down choices and with an initial country database that is part of the system (to be created and updated by you).

After establishing this baseline and narrowing down the choice to a reasonable but not too short list (let’s say 10-20), we need to start asking discriminating questions to shorten the list further.   This will involve using an AI to identify key differences between countries in the list so we can narrow the list (and possibly expand it if we learn key new information).

Once we have a list of 3-5 candidates, we can present the options in a tabular form, like a spreadsheet, with key criteria and tradeoffs explicitly shown to the user.   They can then play with the criteria, add new ones which will populate for all the candidates, request new candidates to be added, remove some, and so on.   It is a spreadsheet-like intelligent playground for the user to explore their new home.   Drilling down on a candidate will reveal maps, photos, and so on from the country, found by doing web searches.

Ultimately the user will choose one or two most likely candidates - and then we want to put them in touch with real estate agents who can help them find their new house.   (For the moment this is just a web search but in the future this will be part of the business model, to actually start the house hunt.)

There will also be a chat dialogue that interacts with the user’s profile, list of candidates and other data, and helps refine and answer questions about the search.   It must be strictly limited to just the subject at hand.   However certain questions about politics are OK because one of the main motivations is to escape shitty politics, prejudice, and so on at home - so questions about political stability and trends in target countries are OK.

Each user will be stored in the database with their profile, search to date, and other relevant information so they can come back into the system later and get back their search context.  The user model is very simple to start with - users can self-register from the home page and have a simple password access.

There is also an admin interface to help manage the system - the full database, the users, the user accesses and queries, and so on.   You can look in ../golden-path/ for an example of a good admin UI.

The user should be able to respond to questions and do the chat with vocal input as well as typed, especially on mobile devices where typing a lot is difficult.

## UI Style

* The application must work fluidly on both desktops and mobile devices.
* The interface should be a simple, modern design.
* Color palette centering on turquoise blue with appropriate other contrasting and homogeneous colours.   The feeling should be welcoming and make the user dream about their new home elsewhere - nothing alarming or off-putting.

## Tech stack

* The back-end will be a Python FastAPI server.
* The database can use Postgres with SQL Lite
* The front-end will be a TypeScript React web app
* The whole thing will run in a Docker compose with containers for the back-end, front-end, and database.
* We are going to develop on a Mac and host it on a Linux server from Scaleway that is also hosting several other apps.   The back-end Docker compose can have an embedded nginx but the production server has an external nginx that must be configured.  Be careful about port conflicts, xCape must have its own ports!   The name of the server is apps.athenadecisions.com.
* For the AI, use the OpenAI Responses API.   Default model is gpt-5.   This will allow you to use web search and other tools.

## Instructions

Think carefully about a good UX and UI for this application that allows friendly, progressive gathering of information, as well as a solid back-end database structure and use of AI to fill in the database and respond to user queries.   Propose a few design mock-ups and ask as many questions as necessary to get the overall system look and feel and back-end structure right.   We intend on using AI and web searches heavily in this application to find up-to-date information, but there should be enough built-in information and local queries to avoid long waits when possible.  Local information will have to be updated regularly, of course.
