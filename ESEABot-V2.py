import pymongo, json, time, threading, random, datetime
from urllib.request import Request, urlopen
from math import ceil

client = pymongo.MongoClient("mongodb+srv://username:password@cluster0.uupdi.mongodb.net/esea?retryWrites=true&w=majority")
cookie = ""

usersArr = []
usersOnlineArr = []
usersInGameArr = []
matchesAdded = []


def addHeaders(url):
    url.add_header("Accept","text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8")
    url.add_header("Accept-Language","en-US,en;q=0.5")
    url.add_header("Cache-Control","max-age=0")
    url.add_header("Connection","keep-alive")
    url.add_header("Cookie",cookie)
    url.add_header("DNT","1")
    url.add_header("Host","play.esea.net")
    url.add_header("TE","Trailers")
    url.add_header("Upgrade-Insecure-Requests","1")
    url.add_header("User-Agent","Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:81.0) Gecko/20100101 Firefox/81.0")
    url.add_header("origin","play.esea.net")
    return url

# Get single user, to get data like match id
def getUser(id):
    url = Request("https://play.esea.net/api/users/" + str(id))
    url = addHeaders(url)

    try:
        content = urlopen(url, timeout=75).read()
    except:
        print("getUser - error")
    else: 
        user = json.loads(content)
        return user

# Get new user list, update DB with online status and get match
def getUserList():
    url = Request("https://play.esea.net/api/site_statuses")
    url = addHeaders(url)

    try:
        content = urlopen(url, timeout=75).read()
    except:
        print("getUserList - site status error")
    else:
        user = json.loads(content)
    page_Count = ceil(user["data"]["ticker"]["stats"]["online"]/100)

    for i in range(1,page_Count+1):
        print("ESEA - Get Users Page " + str(i))
        url = Request("https://play.esea.net/api/whos_online?page_size=100&page="+str(i))
        url = addHeaders(url)
        try:
            content = urlopen(url, timeout=75).read()
        except:
            print("getUserList - page error")
        else:
            usersTemp = json.loads(content)
            usersArr.extend(usersTemp["data"])
    
    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(usersArr, f, ensure_ascii=False, indent=4)

# Set all Users online in DB to offline
def toggleOnlineUsersDB():
    with client:
        db = client["esea"]
        usersOnlineDB = db.users.find({"online_status": {"$eq" : "online"}})
        for user in usersOnlineDB:
            try:
                db["users"].update_one(user, { "$set": { "online_status": "offline"}})
            except:
                print('ERROR - User status not updated')
            else:
                print('Updated Online Status of ' + user["alias"])

# Updates users with current online status
def updateDBUserStatus():
    with client:
        db = client["esea"]
        usersDB = db.users.find()
        for userObjDB in usersDB:
            for userObjArr in usersArr:
                if userObjArr["user"]["id"] == userObjDB["id"]:
                    db["users"].update_one(userObjDB, { "$set": { "online_status": "online"}})
                    try:
                        userObjArr["time_playing"]
                    except:
                        print("no match")
                    else:
                        usersInGameArr.append(userObjArr["user"]["id"])

# Checks usersInGameArr and then removes players in match to avoid duplicates and unnecessary queries
def removeUserList(match):
    for user in match["data"]["team_1"]["players"]:
        if user["id"] in usersInGameArr:
            usersInGameArr.remove(user["id"])
    for user in match["data"]["team_2"]["players"]:
        if user["id"] in usersInGameArr:
            usersInGameArr.remove(user["id"])

# Gets new user data from ESEA and update their tier status
def checkAllTiers():
    with client:
        db = client["esea"]
        users = db.users.find()
        for user in users:
            newUserInf = getUser(user['id'])

            # Checks for tier status compared to DB
            if user["tier"] != newUserInf["data"]["tier"]:
                try:
                    db["users"].update_one(user, { "$set": { "tier": newUserInf["data"]["tier"]}})
                except:
                    print('ERROR - Updating tier Status of ' + user["alias"])
                else:
                    print('ESEA - Updated tier Status of ' + user["alias"])
            
            # Checks for alias compared to DB
            if user["alias"] != newUserInf["data"]["alias"]:
                try:
                    db["users"].update_one(user, { "$set": { "alias": newUserInf["data"]["alias"]}})
                except:
                    print("ERROR - Updating alias of user " + user["alias"] + " to alias: " + newUserInf["data"]["alias"])
                else:
                    print("ESEA - Updated alias of user " + user["alias"] + " to alias: " + newUserInf["data"]["alias"])

# Slows program down a lot, so limited to 4 most recent matches
def checkTier(userID):
    with client:
        db = client["esea"]
        user = db.users.find_one({"id": {"$eq" : userID}})
        if user:
            # Sets it to premium if it's standard
            # Sub status doesn't matter and will get fixed with Tier checked
            if user["tier"] == "standard":
                try:
                    db["users"].update_one(user, { "$set": { "tier": "premium"}})
                except:
                    print("ERROR - Couldn't update tier of " + user["alias"])
                else:
                    print("checkTier - updated tier of " + user["alias"])
        else:
            print("checkTier - User doesn't exist")

# Fetches match from ESEA servers
def getMatch(matchID):
    url = Request("https://play.esea.net/api/match/" + str(matchID))
    url = addHeaders(url)
    try:
        content = urlopen(url, timeout=75).read()
    except:
        print("getMatch - error")
    else:
        match = json.loads(content)

        return match

# Adds match to private DB with match ID
def addMatch(newMatch):
    with client:
        db = client["esea"]
        try:
            db.matches.find({"data.id": {"$eq" : newMatch}})[0]
        except:
            print("No match exists, match will be created")
            newMatchC = getMatch(newMatch)
            print(newMatchC)
            print("---------------------------------------------------------------------------------------------------------------------")
            try:
                db["matches"].insert_one(newMatchC)
            except:
                print("ERROR - Couldn't insert new match")
            else:
                matchesAdded.append(newMatch)
        else:
            if newMatch not in matchesAdded:
                matchesAdded.append(newMatch)
                print("match exists, replacing")
                try:
                    db["matches"].replace_one(db.matches.find({"data.id": {"$eq" : newMatch}})[0], getMatch(newMatch))
                except:
                    print('ERROR - match not replaced')

# Checks for matches in usersInGameArr and then runs addMatch
def getMatches():
    try:
        usersInGameArr[0]
    except:
        print("no users in games")
    else:
        userInf = getUser(usersInGameArr[0])
        #Check for new games being played
        if userInf["data"]["game_status"] is None:
            print("No game, probably done")
            usersInGameArr.remove(usersInGameArr[0])
        else:
            newGameID = userInf["data"]["game_status"]["link"]
            newGameID = newGameID.replace("/match/","")
            print("getMatches - Getting Match")
            usersInGameArr.remove(usersInGameArr[0]) #Fix for looping
            removeUserList(getMatch(int(newGameID)))
            addMatch(int(newGameID))

# Checks DB for active matches and updates them
def checkMatches():
    with client:
        db = client["esea"]
        # Limit to 10 most recent matches
        matches = db.matches.find().sort('_id', -1).limit(10)
        for idx, match in enumerate(matches):
            if match["data"]["completed_at"] is None:
                print("checkMatches - getting new match info")
                newMatchInf = getMatch(match["data"]["id"])
                db["matches"].replace_one(match, newMatchInf)
            else:
                print("checkMatches - match is done")

                # Add non-existent users to database
                for user in match["data"]["team_1"]["players"]:
                    try:
                        db["users"].find({"id": {"$eq" : user["id"]}})[0]
                    except:
                        print("User doesn't exist and will be created.")
                        newUser = getUser(user["id"])
                        try:
                            db["users"].insert_one({'id': int(newUser["data"]["id"]), 'alias': str(newUser["data"]["alias"]), 'tier': str(newUser["data"]["tier"]), 'online_status': str(newUser["data"]["online_status"])})
                        except:
                            print("ERROR - User not created")
                    else:
                        if idx < 3:
                            checkTier(user["id"])

                for user in match["data"]["team_2"]["players"]:
                    try:
                        db["users"].find({"id": {"$eq" : user["id"]}})[0]
                    except:
                        print("User doesn't exist and will be created.")
                        newUser = getUser(user["id"])
                        try:
                            db["users"].insert_one({'id': int(newUser["data"]["id"]), 'alias': str(newUser["data"]["alias"]), 'tier': str(newUser["data"]["tier"]), 'online_status': str(newUser["data"]["online_status"])})
                        except:
                            print("ERROR - User not created")
                    else:
                        if idx < 3:
                            checkTier(user["id"])

# Updates the last time a section has been updated
def updateTime(updateField):
    with client:
        db = client["esea"]
        status = db["status"].find()
        try:
            db["status"].update_one(status[0],{"$set": { updateField: datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")}})
        except:
            print("ERROR - status not updated")

# Threads to have them run at a random time
def threadMatches():
    while True:
        matchesAdded.clear()
        checkMatches()
        updateTime("matches")
        newTime = random.randrange(60,120)
        print("threadMatches - new time: " + str(newTime))
        time.sleep(newTime)

def threadUsers():
    while True:
        usersArr.clear()
        usersOnlineArr.clear()
        usersInGameArr.clear()

        getUserList()
        toggleOnlineUsersDB() 
        updateDBUserStatus()
        print({"usersInGameArr": usersInGameArr})

        while len(usersInGameArr) > 0:
            getMatches()
            print({"usersInGameArr": usersInGameArr})
        print({"usersInGameArr": usersInGameArr})

        updateTime("online_status")

        newTime = random.randrange(720,900)
        print("threadUsers - new time: " + str(newTime))
        time.sleep(newTime)

def threadTiers():
    while True:
        print("threadTiers - Started")
        checkAllTiers()
        updateTime("tiers")
        print("threadTiers - Done")
        time.sleep(432000)

# addMatch()

threading.Timer(1, threadMatches).start()
threading.Timer(1, threadUsers).start()
threading.Timer(432000, threadTiers).start()


# with client:
#     db = client["esea"]
#     status = db["status"].find()
#     print(status[0]["tiers"])
#     print(datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"))
#     print(status[0]["tiers"] - datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"))

# If match needs to be added manually
# 
# addMatch(matchID)

# Program Flow:
#
# Get User list and add to array usersOnlineArr
# - getUserList()
# Make all current online users in DB to offline
# - toggleOnlineUsersDB()
# Update users in DB from array usersOnlineArr 
# - updateDBUserStatus()
# Check usersInGameArr for games. Remove if not in game / add match code to currentMatches array if they are
# - getMatches()
# 
# Check old matches and update running ones while limiting DB to latest
# - checkMatches()
