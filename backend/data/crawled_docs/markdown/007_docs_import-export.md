# Import/Export | 4ga Boards Docs

Source: https://docs.4gaboards.com/docs/import-export

# Import/Export
## Import from Trello[​](https://docs.4gaboards.com/docs/import-export/#import-from-trello "Direct link to Import from Trello")
Are you migrating from other software?  
Currently 4ga Boards is supporting migration from Trello. To do this, export your Trello board in .json format (the only one included in the free version of Trello) and do the following:
  1. Create new board and select "Import":


![Board creation popup window](https://docs.4gaboards.com/assets/images/boardcreate_en-dec32a5ab0362b083076298ee8be6f57.png)
  1. Select appriopriate option for import:


![Board import popup window](https://docs.4gaboards.com/docs/import-export/)
  1. In the file manager select the appriopriate `.json` file, name your new board and choose in which project it should be created. Think of the project for now as kind of Trello's workspaces - a container that holds boards. More on project [here](https://docs.4gaboards.com/docs/project).


![Trello import options](https://docs.4gaboards.com/assets/images/importboardtrello_en-0c8c5b7334066e7008903d1f8c567cea.png)
And done! Now you have a fully functioning board - also with labels!
## Import from 4ga Boards[​](https://docs.4gaboards.com/docs/import-export/#import-from-4ga-boards "Direct link to Import from 4ga Boards")
Changing instances or copying board from another user?  
With the 4ga Boards import you can quickly setup your workspace. Be sure you have an appriopriate 4ga Boards export file (it should have a `.tgz` format) and do the following:
  1. Create new board and select "Import":


![Board creation popup window](https://docs.4gaboards.com/assets/images/boardcreate_en-dec32a5ab0362b083076298ee8be6f57.png)
  1. Select appriopriate option for import:


![Board import popup window](https://docs.4gaboards.com/docs/import-export/)
  1. In the file manager select the appriopriate .tgz file, name your new board and choose in which project it should be created. Here you can also check two options regarding users:
     * `Add project managers`: New managers will be added to the project if they had the same role in the exported board.
     * `Create accounts for non-existing users`: New accounts will be created for users that does not exist in the current 4ga Boards instance, but were members of the board in the exported board.


![4ga Boards import options](https://docs.4gaboards.com/assets/images/importboard4ga_en-42f739f0c2b1e8364f975e133ea3f0c5.png)
## Export[​](https://docs.4gaboards.com/docs/import-export/#export "Direct link to Export")
Exporting in 4ga Boards is quick and easy. Simply open the context menu of the board you wish to export and select the `Export Board` option. Save the resulting `.tgz` file to your preferred location.
![Board context menu](https://docs.4gaboards.com/assets/images/boardmenu_en-504faa17880e8a0cf3c6465fc648b2f8.png)