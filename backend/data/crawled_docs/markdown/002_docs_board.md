# Board | 4ga Boards Docs

Source: https://docs.4gaboards.com/docs/board

# Board
The heart of 4ga Boards is, unsuprisingly, a board. Board view is the main view of this app - you will spend here most of your time. Don't worry! It's easy to grasp. At first you will see that your project contains no boards - to create them, simply click the `+Add Board` button that is located at the bottom of the sidebar or at the top-right corner of the screen.
![Empty board view](https://docs.4gaboards.com/assets/images/boardviewempty_en-07726b7b56ac4c5f3992de859abd8020.png)
If you are joining to an existing project, here is how it should look like:
![Board view showing &quot;New website&quot; board](https://docs.4gaboards.com/assets/images/mainviewgettingstarted_en-e6ac5245c2d24b3adf601cd30bf695de.png)
If you have set the default view as list view, here is what you will see:
![List view showing the &quot;New website&quot; board](https://docs.4gaboards.com/assets/images/listview_en-c26bbc2fc4100bada795e3162a7fd767.png)
Notice that selected board is highlighted in the sidebar view (in this case, it is "New Website" from "Marketing" project).
## Creating a new board[​](https://docs.4gaboards.com/docs/board/#creating-a-new-board "Direct link to Creating a new board")
There can be more than one board per project - simply click the `+Add Board` button that is located at the top-right corner of the screen to create new one inside the currently opened project. Alternatively you can add board using three-dot sidebar menu of a [project](https://docs.4gaboards.com/docs/project) (it will create the board inside the selected project). The last option is to click the `+Add Board` button at the bottom of the sidebar. This will enable additional setting - choosing the project in which the board will be created from the dropdown list.
![Buttons placement for creating a new board](https://docs.4gaboards.com/assets/images/boardaddbutton_en-aac00e89337ce0287096168656a167a9.png)
This will open up a pop-up window in which you can name your board, prefill the lists in the board with templates or import your data from 4ga Boards (in .csv file format) or from Trello (supporting .json file format).
![Board creation popup window](https://docs.4gaboards.com/assets/images/boardcreate_en-dec32a5ab0362b083076298ee8be6f57.png)
Currently there are two available templates, simple:
![Simple board template](https://docs.4gaboards.com/assets/images/boardsimple_en-0f292f3e2a9e4a289b9f9812a6ed05e3.png)
And kanban:
![Kanban board template](https://docs.4gaboards.com/assets/images/boardkanban_en-0d8d53e96c30dd857eccd63f138e8d29.png)
## Board additional options[​](https://docs.4gaboards.com/docs/board/#board-additional-options "Direct link to Board additional options")
If you want to edit or delete your board, open the ellipsis menu in the sidebar (they will show after you hover over the board name). You can also change the order of the board within the project after clicking and holding the two arrows button that will appear on the left of the board name. If you wish, you can also export your board in .csv format here.
![Popup menu with board settings](https://docs.4gaboards.com/assets/images/boardmenu_en-504faa17880e8a0cf3c6465fc648b2f8.png)
## Board toolbar[​](https://docs.4gaboards.com/docs/board/#board-toolbar "Direct link to Board toolbar")
Each board comes with separate toolbar, in which (going from left to right) you can:
  1. Set up GitHub integration (click GitHub icon),
  2. See the number of cards after filtering,
  3. Add members to the board `+Add member` icon, delete or edit permissions of members (click on the appriopriate member icon to change it),
  4. Filter cards (more below the image),
  5. Change view (Board view/List view)


![Board toolbar](https://docs.4gaboards.com/assets/images/boardtoolbar_en-2eb3876798033c97133ed1b2a1a0795c.png)
## Board Filtering[​](https://docs.4gaboards.com/docs/board/#board-filtering "Direct link to Board Filtering")
Board filtering is a powerful tool that let's you quickly find what you are looking for. For even quicker navigation, you can select appriopriate option (explained below) by clicking or using key combination when you are clicked in the `Filter cards` type box.
You can filter board using different techniques:
  1. `Aa`: Match Case (`Alt` + `C`): will filter based on letter case (Example: typing "create" will not return cards with the title "Create")
  2. `~`: Any Match (`Alt` + `V`): "inclusive search"; Enable this option to show cards that match any of your selected filters.  
(Example: If you select multiple members, the search will return every card that has at least one of the selected members assigned. If `Any Match` is off, only cards that have all selected members assigned will appear.)
  3. Filter by members: Select/Remove members you want to filter.
  4. Filter by labels: Select/Remove labels you want to filter.
  5. Filter by due date: Select the due date to filter: search will return all the cards that are _before_ selected due date; if `Show Cards Just For Selected Day` option is enabled, it will show cards with only the _exact_ due date. This search returns also the cards with appriopriate subtask due date.


## Board permissions[​](https://docs.4gaboards.com/docs/board/#board-permissions "Direct link to Board permissions")
Each member of the board can have different permission:
  * Project manager: manage boards and add members,
  * Editor: can create and delete tasks and lists,
  * Commenter: can view contents of the board and comment on the cards,
  * Viewer: can only view contents of the board.