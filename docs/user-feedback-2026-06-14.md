# User Feedback

## Introduction

Here is a collection of user feedback from a testing session today.   I have tried to organise it by general area with both observations and tentative recommendations.   I would like you to consolidate the information, think about it carefully, and a propose a plan that addresses the usability and other concerns mentioned - not necessarily the specific proposal I might make but one that integrates the whole thing.

## Reasons for Leaving

* In addition to other reasons for leaving there is also "protection du patrimoine” and “retirement”.

## Priorities

* The questions come too late in the process, should come early in the questionnaire.
* Between reasons for leaving and priorities in new country, we can establish a profile of what criteria are probably important to the user.   So these should be filters on what criteria questions are asked and a means to weight the criteria appropriately.
* Should allow any number of priorities, not just 3, and also free text.

## Communities:

* Immigrants not a good community - in the new country, the user will be an immigrant (by definition) so concerns for the local immigrant community are not meaningful.   Potentially something interesting around general atmosphere for immigrants in the new country as a criteria on its own but that is not a community concern.
* Add other religions?  Christians (of different sects?) or just a category for “other religious minorites”.   Maybe something about the religious makeup of the target country and how it matches the religion (if any) of the user.   But we don’t want to overwhelm the user with a choice of communities that don’t represent a good % of real users.   Maybe an open text field is OK to explain the concerns and use it as a prompt to the AI.

## Criteria

* Rent or buy not that important - this is only really important when doing the detailed cost of living analysis.
* The words chosen for criteria values are often a bit off or weird.   For example “contrasté” for tolérance et inclusion is not clear at all.   I added a custom criteria “Proximité” which uses “bon” and “faible” as values but really we want “Near” (good) and “Far” (bad).
* Proximité should be a built-in criteria.
* Criteria can't really be a flat list.   They should have categories (e.g. the priorities / reasons for leaving) and maybe multiple levels.   For instance under “job” we could have “unemployment in my sector”, “average pay”, “ease of finding a job in my industry”, and several other sub-criteria that are only exposed if the user wants to click down into a category more deeply.  Another example, under health care or santé, there is a question of quality of care, ease of access, cost of care, etc which might be differentially of interest depending on the user’s situation.  Currently it is summarised as “solide” or “bon” which are very generic.
* Multiple climates are acceptable - generally most criteria should have a range or multiple values allowed (and probably this is a per-criteria parameter)
* When a certain category is important to a user (e.g. religious minority tolerance or ant-semitism), more information should be provided in the relevant criteria justifications / explanations.
* Personalised criteria don’t appear in the user’s profile and don’t seem to influence the score calculation.
* When adding a personalised criteria, the AI goes off into a long wait - would be better to update the UI first, show the waiting animation in the criteria values and fill it when computed, to provide more reassurance to the user that their new criteria is taken into account.
* Right now the criteria weights in the profile criteria management page are symbolic values so the user can’t know or control how the actual score formula works - should show (and allow user to directly enter) the actual weights for the values to provide more control and understanding.
* Not all the criteria need to be shown systematically in the comparison table - just show the 5 with the highest weights and let the others be in a collapsed part of the table.   Don’t show criteria with 0 weight.

## Evaluation

* The wait time to analyse a country is super slow.   We need to have a way to reanalyse more countries with predefined criteria to avoid doing more slow searches.
* Country criteria search results can be analysed offline in a separate process?
* In response to the observation that doing a full analysis for a country is too slow - There should be a cross-user cache of country / criteria analyses from the AI that includes a simple score, a justification, and possibly sources.   The cache should be dirtied occasionally to ensure up-to-date information (maybe once a month? Or dirtied / set by admin?)
* Right now the set of countries that actually gets chosen is suspiciously small.  I suspect the database is not fleshed out as it should be.  Need to verify the incompleteness.
* New criteria don’t seem to get analysed at all for the home country, need a comparison point.
* No countries seem to have an existing or found value for “égalité homme / femme” which is another clue that the database is underpopulated and not auto-updating progressively.

## UI

* The AI can be slow and the affordance for waiting is too subtle and doesn’t help the user be patient.   We need to give them more incentive to wait and show the animation better, maybe with a timer or with little messages or some intermediate results?
* The popup for a criterion value for a country should show the longer justification as well as the score without having to go to “show details” and wait for the very long full analysis.
* In the evaluation table, in French, tried adding a new country “Espagne” but nothing happened.  There were already five countries in the table, is that the reason?  Or is it the French country name?   Or something else?
* Related point, adding a new country shouldn’t be free text but rather selecting from a list with substring filtering.
* The ability to manage criteria, set their weight, describe them better, etc is valuable but too hidden in the profile now.  Should be somewhat more prominent in the comparison table page as an affordance.  Maybe clicking on a criterion name could be the way?  But also a message as there already is for clicking on countries & criteria values.
* Should be a “Help” button with some screens on how the system works.
* Vocal ninput ot working on iPhone Firefox or iPhone safari (two different iPhones).  The microphone turns red and at least for Safari the phone asked permission to use the microphone, but no transcription occurred.   On Mac / Chrome it works fine.   Also the microphone affordance is small and very close to the Enter arrow which creates fat finger issues.



