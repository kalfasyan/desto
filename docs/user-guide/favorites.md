# Favorite Commands

**Save, organize, and quickly run your frequently used commands!**

The Favorites feature lets you save commands you run regularly, so you can execute them with a single click instead of setting them up every time.

## Getting Started

### Saving a Command as Favorite

1. In the **Scripts** tab, set up your command:
   - Select a script from the dropdown
   - Enter any arguments
   - (Optional) Enter a session name

2. Click the **"Save as Favorite"** button (⭐)

3. A dialog will appear asking for a name for your favorite:
   - Enter a descriptive name (e.g., "deploy", "backup", "daily-report")
   - Click **Save**

That's it! Your favorite is now saved and ready to use.

### Running a Favorite

1. Click the **Favorites** tab in the dashboard

2. Find your favorite in the list

3. Click the **▶️ Run** button to execute the command

The command will:
- Start a new tmux session with the name `fav-{your-favorite-name}`
- Automatically increment the usage counter
- Appear in your sessions list

### Managing Favorites

#### Search

Use the search box at the top of the Favorites tab to filter by:
- Favorite name
- Command content

#### Edit

1. Click the **✏️ Edit** button on any favorite
2. Update the name or command
3. Click **Save**

#### Delete

1. Click the **🗑️ Delete** button on any favorite
2. Confirm the deletion
3. Your favorite is removed

### Favorite Statistics

For each favorite, you'll see:
- **Usage count**: How many times you've run this favorite
- **Last used**: When this favorite was last executed (if ever)

The Favorites tab sorts commands by most-used first, so your go-to commands appear at the top.

## Features

✅ **Persistent storage** - All favorites are saved in Redis and survive application restarts  
✅ **Quick search** - Filter favorites by name or command content  
✅ **Usage tracking** - See which commands you use most  
✅ **Duplicate prevention** - Can't accidentally create two favorites with the same name  
✅ **Full command preservation** - Saves the complete execution command with all arguments  
✅ **Named sessions** - Each favorite execution gets a descriptive session name

## Examples

### Save a Deploy Command

1. Select `deploy.sh` script
2. Add arguments: `--production --verify`
3. Name it: **"deploy-prod"**
4. Click "Save as Favorite"

Later, just click the Run button to deploy to production with one click!

### Save a Data Processing Pipeline

1. Select `process.py` script
2. Add arguments: `--input=/data/raw --output=/data/processed --format=csv`
3. Name it: **"process-daily"**
4. Click "Save as Favorite"

### Save a Health Check

1. Select `health-check.sh` script
2. Add arguments: `--services=api,db,cache`
3. Name it: **"check-services"**
4. Click "Save as Favorite"

## Tips & Tricks

💡 **Naming convention**: Use descriptive names with hyphens (e.g., `backup-daily`, `test-suite`, `build-prod`)

💡 **Edit instead of recreate**: If you want to modify a command slightly, edit the favorite rather than creating a new one

💡 **Search shortcuts**: 
- Search for `python` to find all Python-based favorites
- Search for `--prod` to find production commands

💡 **Usage tracking**: Check the usage count to identify which commands are actually being used vs which are rarely run

## Under the Hood

Favorites are stored in Redis using the following structure:

- **favorite_id**: Unique UUID identifier
- **name**: User-friendly display name
- **command**: Full execution command
- **created_at**: When the favorite was created
- **last_used_at**: Last execution timestamp
- **use_count**: Number of times run

This ensures your favorites are persistent, searchable, and always available.
