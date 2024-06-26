"GRIFOUILLE !!!"
from asyncio import TimeoutError as TE
from typing import NoReturn
from time import sleep
from string import ascii_uppercase
from datetime import datetime, timedelta
from random import randrange, random, choice


from interactions import Client, Status, Activity, ActivityType, SlashCommandChoice, OptionType, Modal, SlashCommandOption, File, SlashContext, ShortText, slash_command, ModalContext
from interactions.models.discord.emoji import CustomEmoji
from interactions.ext.files import command_send


from lib import load_json, save_json, create_char, get_personnas, get_scene_list, create_stats, display_stats, count_crit_values
from pygsheets import authorize
from obs_interactions import obs_invoke, toggle_anim
from gsheets_interactions import values_from_player, stat_from_player, hero_point_update, increase_on_crit, get_stress, update_char, get_url

#############################
### Chargement des tokens ###
#############################

# tokens OBS-WS
tokens_obsws: dict = load_json("obs_ws")
host: str = tokens_obsws["host"]
port: int = tokens_obsws["port"]
password: str = tokens_obsws["password"]

# tokens discord
tokens_connexion: dict = load_json("token_frimousse")
token_grifouille: str = tokens_connexion['token']

# déclaration du client
bot = Client(
    token=token_grifouille,
    status=Status.ONLINE,
    activity=Activity(
        name="des pôtichats",
        type=ActivityType.PLAYING,
    )
)

patounes_love = CustomEmoji(
    _client=bot,
    name="patounes_heart",
    id=979510606216462416
)

# tokens GSheets
gc = authorize(service_file='env/connect_sheets.json')

# datas d'environnement
dict_stats: dict = load_json("stats")
dict_pos: dict = load_json("pos")
dict_links: dict = load_json("links")
dict_stress: dict = load_json("stress")
embed_projets: dict = load_json("embed_projets")
embed_jdr: dict = load_json("embed_jdr")
quotes: dict = load_json("quotes")

# préparation du dico de stress
listStates = [key for key in dict_stress.keys()]
listEffects = [value for value in dict_stress.values()]

# liste des scènes disponibles au switch
list_of_scenes: list = get_scene_list(tokens_obsws)[:20]
abbrev_scenes: list = [sc[:20] if len(
    sc) > 20 else sc for sc in list_of_scenes]

# listes utiles à déclarer en amont
list_letters: list = [
    "\U0001F1E6",
    "\U0001F1E7",
    "\U0001F1E8",
    "\U0001F1E9",
    "\U0001F1EA",
    "\U0001F1EB",
    "\U0001F1EC",
    "\U0001F1ED",
    "\U0001F1EE",
    "\U0001F1EF",
    "\U0001F1F0",
    "\U0001F1F1",
    "\U0001F1F2",
    "\U0001F1F3",
    "\U0001F1F4",
    "\U0001F1F5",
    "\U0001F1F6",
    "\U0001F1F7"
]


list_days: list = [
    "Lundi",
    "Mardi",
    "Mercredi",
    "Jeudi",
    "Vendredi",
    "Samedi",
    "Dimanche"
]

manuels: list = ["one_shot"]
competence_choices: list = [
    SlashCommandChoice(
        name=val,
        value=val
    ) for val in [
        "Constitution",
        "Intelligence",
        "Force",
        "Conscience",
        "Agilité",
        "Social"
    ]
]

competence_pos: dict = {
    "Constitution": "F3",
    "Intelligence": "F4",
    "Force": "F5",
    "Conscience": "F6",
    "Agilité": "F7",
    "Social": "F8"
}


stats_choices: list = [
    SlashCommandChoice(
        name=val,
        value=val
    ) for val in dict_stats.values()
]
char_choices: list = [
    SlashCommandChoice(
        name=val,
        value=key
    ) for key, val in get_personnas().items()
]

#################### Créer un personnage ##################


@slash_command(
    name="create_char",
    description="Génère les caractéristiques d'un personnage aléatoire !",
    options=[
        SlashCommandOption(
            name="ethnie",
            description="Type de personnage à générer",
            type=OptionType.STRING,
            choices=char_choices,  # type:ignore
            required=True,
        ),
    ],
)
async def generate_char(ctx, ethnie: str):
    "Génère les caractéristiques d'un PNJ aléatoire"
    await command_send(
        ctx=ctx,
        content='\n'.join(
            [f"*{k}*  -->  **{v}**" for k, v in create_char(ethnie).items()]
        ), files=File(
            create_stats()  # type:ignore
        )
    )

################ Pour sauvegarder la fiche #################


@slash_command(
    name="save_file",
    description="Sauvegarde un lien avec une fiche de statisitiques"
)
async def save_file(ctx: SlashContext):
    "Appel au modal pour enregistrer un lien vers une fiche de personnage"
    sheet_modal = Modal(
        ShortText(
            label="Entrez le nom de votre fiche sur GoogleSheets",
            custom_id="sheet_name"
        ),
        title="Lier une feuille de stats",
    )
    await ctx.send_modal(modal=sheet_modal)
    try:
        # Parsing de la modal
        return_modal: ModalContext = await bot.wait_for_modal(modal=sheet_modal, author=ctx.author.id, timeout=60)
    except TE:
        # Trop long temps de réponse
        return await ctx.send("Tu as pris plus d'une minute pour répondre !", ephemeral=True)
    response = return_modal.responses.get('sheet_name')
    if response is None:
        # L'utilisateur a laissé le champ vide
        return await ctx.send("Tu as laissé un champ vide !", ephemeral=True)
    else:
        # On tente d'accéder la fiche, si on y parvient on sauvegarde
        url = get_url(ctx.author.mention, dict_links, gc)
        if url is None:
            # Si l'URL vaut rien : il y a une erreur quant à la fiche
            return await ctx.send("Le nom de fiche n'est pas valide !", ephemeral=True)
        else:
            # La fiche est valide
            dict_links[f"{ctx.author.mention}"] = f"{response}"
            save_json('links', dict_links)
            return await ctx.send(f"La fiche nommée {response} à l'URL {url} vous a été liée ! {patounes_love}", ephemeral=True)


################ Pour lancer un dé #################


def roll_the_dice(message, faces, modificateur: int = 0, valeur_difficulte: int = 0, hero_point: bool = False, stat_testee: str = "") -> tuple:
    """Lance un dé dans la stat testée et renvoie le résultat.

    Args:
        message (_type_): _description_
        faces (_type_): _description_
        modificateur (int, optional): _description_. Defaults to 0.
        valeur_difficulte (int, optional): _description_. Defaults to 0.
        hero_point (bool, optional): _description_. Defaults to False.
        stat_testee (str, optional): _description_. Defaults to "".

    Returns:
        tuple: chaîne décrivant le résultat et nom de l'anim à envoyer
    """
    res = randrange(1, faces)  # jet de dé
    value = res + modificateur  # valeur globale du jet
    if stat_testee != "":
        stat_testee = f"({stat_testee})"
        if hero_point_update(message.author.mention, dict_links, gc, hero_point):
            value += modificateur
    if valeur_difficulte > 0:
        if res == faces:
            anim = "R_CRIT.avi"
            str_resultat = f"{message.author.mention} > **REUSSITE CRITIQUE** {stat_testee}\n> {res}/{faces} (dé) + {modificateur} (bonus) = **{value}** pour une difficulté de **{valeur_difficulte}**\n> *{choice(quotes['REUSSITE CRITIQUE'])}*"
        elif res == 1:
            anim = "E_CRIT.avi"
            str_resultat = f"{message.author.mention} > **ECHEC CRITIQUE** {stat_testee}\n> {res}/{faces} (dé) + {modificateur} (bonus) = **{value}** pour une difficulté de **{valeur_difficulte}**\n> *{choice(quotes['ECHEC CRITIQUE'])}*"
        elif value >= valeur_difficulte:
            anim = "R_STD.avi"
            str_resultat = f"{message.author.mention} > **REUSSITE** {stat_testee}\n> {res}/{faces} (dé) + {modificateur} (bonus) = **{value}** pour une difficulté de **{valeur_difficulte}**\n> *{choice(quotes['REUSSITE'])}*"
        else:
            anim = "E_STD.avi"
            str_resultat = f"{message.author.mention} > **ECHEC** {stat_testee}\n> {res}/{faces} (dé) + {modificateur} (bonus) = **{value}** pour une difficulté de **{valeur_difficulte}**\n> *{choice(quotes['ECHEC'])}*"
    else:
        anim = "INCONNU.avi"
        str_resultat = f"{message.author.mention} > **INCONNU** {stat_testee}\n> Le résultat du dé est **{value}** ({res}/{faces}+{modificateur}) !\n> *{choice(quotes['INCONNU'])}*"
    return (str_resultat, anim)


@slash_command(
    name="caracteristique",
    description="Permet de changer une valeur sur votre fiche de stats.",
    options=[
        SlashCommandOption(
            name="competence",
            description="Caractéristique à modifier !",
            type=OptionType.STRING,
            choices=competence_choices,
            required=True,
        ),
        SlashCommandOption(
            name="ajouter",
            description="Nombre à ajouter à la caractéristique",
            type=OptionType.INTEGER,
            required=False,
        ),
        SlashCommandOption(
            name="soustraire",
            description="Nombre à soustraire à la caractéristique",
            type=OptionType.INTEGER,
            required=False,
        ),
        SlashCommandOption(
            name="fixer",
            description="Nombre auquel fixer la caractéristique",
            type=OptionType.INTEGER,
            required=False,
        ),
    ],
)
async def caracteristique(ctx: SlashContext, competence: str, ajouter=None, soustraire=None, fixer=None):
    if not (ajouter is None and soustraire is None and fixer is None):
        await ctx.defer()

        values = values_from_player(ctx.author.mention, dict_links, gc)
        labels: list = list(values.keys())
        valeurs_max: list = [values[label]['valeur_max']
                             for label in labels]
        valeurs_actuelle: list = [values[label]
                                  ['valeur_actuelle'] for label in labels]
        valeurs_critique: list = [values[label]
                                  ['seuil_critique'] for label in labels]
        nb_val_critique, zero_stats = count_crit_values(
            valeurs_actuelle, valeurs_critique)

        print(values)

        pos: int = labels.index(competence)
        if fixer is not None:
            future_value: int = max(min(fixer, valeurs_max[pos]), 0)
        else:
            future_value: int = valeurs_actuelle[pos]
        if ajouter is not None:
            future_value = min(future_value + ajouter, valeurs_max[pos])
        if soustraire is not None:
            future_value = max(future_value-soustraire, 0)

        update_char(ctx.author.mention, dict_links, gc, competence_pos, competence,
                    future_value)

        values = values_from_player(ctx.author.mention, dict_links, gc)
        labels: list = list(values.keys())
        new_valeurs: list = [values[label]
                             ['valeur_actuelle'] for label in labels]
        new_critique: list = [values[label]
                              ['seuil_critique'] for label in labels]
        new_count, new_zero = count_crit_values(new_valeurs, new_critique)
        if new_count > nb_val_critique or new_zero > zero_stats:
            # si il y a un changement d'état, qui empire
            if new_count >= 3 or new_zero >= 2:
                await obs_invoke(toggle_anim, host, port, password, "Mort.avi")
            elif new_count <= 2 or new_zero == 1:
                await obs_invoke(toggle_anim, host, port, password, "Portes_Mort.avi")
        await ctx.send(f"La valeur de **{competence}** de {ctx.author.mention} a été changée de **{valeurs_actuelle[pos]}** à **{future_value}** !\nTu as {new_count} valeurs en dessous du seuil critique, dont {new_zero} valeurs à zéro.")


@bot.command(
    name="link",
    description="Renvoie le lien vers la fiche personnage liée, ou un message si aucune fiche n'est liée.",
    scope=guild_id,
)
async def link(ctx: interactions.CommandContext):
    await ctx.defer()
    try:
        await ctx.send(f"Voici l'URL de ta fiche personnage liée ! {patounes_love}\n{get_url(ctx.author.mention, dict_links, gc)}", ephemeral=True)
    except Exception:
        await ctx.send("Désolé, tu ne semble pas avoir de fiche liée. N'hésite pas à en lier une avec **/save_file** !", ephemeral=True)


@bot.command(
    name="display",
    description="Affiche les statistiques actuelles de la fiche active.",
    scope=guild_id,
)
async def display(ctx: interactions.CommandContext):
    await ctx.defer()
    try:
        values = values_from_player(ctx.author.mention, dict_links, gc)
        labels: list = list(values.keys())
        valeurs_max: list = [values[label]['valeur_max'] for label in labels]
        valeurs_actuelle: list = [values[label]
                                  ['valeur_actuelle'] for label in labels]
        valeurs_critique: list = [values[label]
                                  ['seuil_critique'] for label in labels]
        path: str = display_stats(
            labels, valeurs_actuelle, valeurs_max, valeurs_critique)
        crit, zero = count_crit_values(valeurs_actuelle, valeurs_critique)
        await command_send(ctx, f"Voici les stats actuelles de {ctx.author.mention}.\nTu as {crit} valeurs en dessous du seuil critique, dont {zero} valeurs à zéro.", files=interactions.File(filename=path))

    except ConnectionError:
        message = ConnectionError(
            f"Impossible d'atteindre la fiche pour {ctx.author.mention}.")
    except ValueError:
        message = ValueError(
            f"Désolé {ctx.author.mention}, tu ne sembles pas avoir de fiche liée dans ma base de données.")


@bot.command(
    name="stat",
    description="Jet d'un dé accordément à votre fiche de stats !",
    scope=guild_id,
    options=[
        SlashCommandOption(
            name="charac",
            description="Caractéristique à tester !",
            type=OptionType.STRING,
            choices=stats_choices,
            required=True,
        ),
        SlashCommandOption(
            name="valeur_difficulte",
            description="Palier à atteindre pour considérer le jet réussi",
            type=OptionType.INTEGER,
            required=False,
        ),
        SlashCommandOption(
            name="point_heroisme",
            description="Point rendant le jet automatiquement réussi",
            type=OptionType.BOOLEAN,
            required=False,
        ),
    ],
)
async def stat(ctx: SlashContext, charac: str, valeur_difficulte: int = -1, point_heroisme: bool = False):
    """Lance un dé d'une statistique associée à une fiche google sheets

    Args:
        ctx (interactions.CommandContext): contexte d'envoi du message
        charac (str): la caractéristique à tester
        valeur_difficulte (int, optional): difficulté à battre ou égaler pour que le jet soit une réussite. Defaults to -1.
        point_heroisme (bool, optional): stipule si on tente d'utiliser son point d'héroïsme. Defaults to False.
    """
    await ctx.defer()
    message = ""
    try:
        values = stat_from_player(ctx.author.mention, dict_links, gc, charac)[
            2:].split('+')
        message, anim = roll_the_dice(ctx, int(float(values[0].replace(',', '.'))), int(
            values[1]), valeur_difficulte, hero_point=point_heroisme, stat_testee=charac)
        await obs_invoke(toggle_anim, host, port, password, anim)
    except ConnectionError:
        message = ConnectionError(
            f"Impossible d'atteindre la valeur de {charac} pour {ctx.author.mention}.")
    except ValueError:
        message = ValueError(
            f"Désolé {ctx.author.mention}, tu ne sembles pas avoir de fiche liée dans ma base de données.")
    finally:
        await ctx.send(str(message))


def roll_the_stress(message, val_stress, player_has_file: bool = True):
    """
    Lance un dé de stress et en traite les conséquences

    Keywords arguments:
    *message* (discord.message) > source de la commande
    *val_stress* (str) > valeur du stress indiqué dans le message
    *player_has_file* (bool) > si le joueur a une fiche qui lui est associée
    """
    if player_has_file:
        val_max: int = 10
    else:
        val_max: int = 30
    dice: int = randrange(1, val_max)
    index: int = dice + int(val_stress)
    state, anim = listStates[index], str(
        listStates[index])[:-2]+".avi"
    effect = listEffects[index]

    if (dice >= 0.8*val_max):
        "Effet de stress négatif"
        quote = choice(quotes["STRESS NEGATIF"])
        if player_has_file:
            increase_on_crit(str(message.author.mention),
                             dict_links, gc, 'Stress', dict_pos,  1)
    elif (dice <= 0.2*val_max):
        "Effet de stress positif"
        quote = choice(quotes["STRESS POSITIF"])
        if player_has_file:
            increase_on_crit(str(message.author.mention),
                             dict_links, gc, 'Stress', dict_pos,  -1)
    else:
        "Effet de stress médian"
        quote = choice(quotes["STRESS NEUTRE"])

    string = f"{message.author.mention} > **{state}**\n> {dice+1} (dé) : {effect}\n> *{quote}*"
    return (string, anim)


@bot.command(
    name="stress",
    description="Lance un jet de stress !",
    scope=guild_id,
)
async def stress(ctx: interactions.CommandContext):
    """_summary_

    Args:
        ctx (interactions.CommandContext): _description_
    """
    message = ""
    await ctx.defer()
    try:
        message, anim = roll_the_stress(
            ctx, get_stress(ctx.author.mention, dict_links, gc))
        await ctx.send(message)
        await obs_invoke(toggle_anim, host, port, password, anim)
    except:
        try:
            message, anim = roll_the_stress(ctx, 0, False)
        except ConnectionError:
            message = ConnectionError(
                f"Impossible d'atteindre la valeur de stress pour {ctx.author.mention}.")
        except ValueError:
            message = ValueError(
                f"Désolé {ctx.author.mention}, tu ne sembles pas avoir de fiche liée dans ma base de données.")
    finally:
        await ctx.send(str(message))


@bot.command(
    name="dice",
    description="Simule un dé à n faces !",
    scope=guild_id,
    options=[
        interactions.Option(
            name="faces",
            description="Nombre de faces du dé à lancer",
            type=interactions.OptionType.INTEGER,
            required=False,
        ),
        interactions.Option(
            name="modificateur",
            description="Opérateur et valeur",
            type=interactions.OptionType.INTEGER,
            required=False,
        ),
        interactions.Option(
            name="valeur_difficulte",
            description="Palier à atteindre pour considérer le jet réussi",
            type=interactions.OptionType.INTEGER,
            required=False,
        ),
        interactions.Option(
            name="point_heroisme",
            description="Point rendant le jet automatiquement réussi",
            type=interactions.OptionType.BOOLEAN,
            required=False,
        ),
    ],
)
async def dice(ctx: interactions.CommandContext, faces: int = 20, modificateur: int = 0, valeur_difficulte: int = -1, point_heroisme: bool = False):
    await ctx.defer()
    message, anim = roll_the_dice(
        ctx, faces, modificateur, valeur_difficulte, point_heroisme)
    await ctx.send(message)
    await obs_invoke(toggle_anim, host, port, password, anim)


@bot.command(
    name="toss",
    description="Lance une pièce !",
    scope=guild_id,
)
async def toss(ctx: interactions.CommandContext) -> None:
    await ctx.defer()
    res = "**PILE**" if (random() > 0.5) else "**FACE**"
    await ctx.send(f"{ctx.author.mention} > La pièce est tombée sur {res} !\n> *Un lancer de pièce, pour remettre son sort au destin...*")


@bot.command(
    name="calendar",
    description="Crée un sondage de disponibilités",
    scope=guild_id,
    options=[
        interactions.Option(
            name="duree",
            description="Nombre de jours sur lequel s'étend le sondage. Maximum : 12, défaut : 7.",
            type=interactions.OptionType.INTEGER,
            required=False,
        ),
        interactions.Option(
            name="delai",
            description="Décalage de début du sondage (en jours). Défaut : 0.",
            type=interactions.OptionType.INTEGER,
            required=False,
        ),
        interactions.Option(
            name="titre",
            description="Texte de titre du sondage.",
            type=interactions.OptionType.STRING,
            required=False,
        ),
        interactions.Option(
            name="mentions",
            description="Petit texte en-dessous pour mentionner des rôles, ou donner des détails.",
            type=interactions.OptionType.STRING,
            required=False,
        ),
    ],
)
async def calendar(ctx: interactions.CommandContext, duree: int = 7, delai: int = 0, titre: str = "Date pour la prochaine séance !", mentions: str | None = None) -> None:
    """Crée un calendrier sous forme d'embed, pour faire un sondage sur les jours suivants

    Args:
        ctx (interactions.CommandContext): contexte de la commande
        days (int, optional): Période de temps sur laquelle s'étend le sondage. Defaults to 7.
        offset (int, optional): Décalage en jours. Defaults to 0.
        description (str, optional): Un titre pour le sondage. Defaults to "Date pour la prochaine séance !".
    """
    nb_jours: int = duree if duree <= 12 and duree > 0 else 7
    decalage: int = delai if delai >= 0 else 0
    list_days: list = ["Lundi", "Mardi", "Mercredi",
                       "Jeudi", "Vendredi", "Samedi", "Dimanche"]
    list_letters: list = ["\U0001F1E6", "\U0001F1E7", "\U0001F1E8", "\U0001F1E9", "\U0001F1EA", "\U0001F1EB", "\U0001F1EC", "\U0001F1ED",
                          "\U0001F1EE", "\U0001F1EF", "\U0001F1F0", "\U0001F1F1", "\U0001F1F2", "\U0001F1F3", "\U0001F1F4", "\U0001F1F5", "\U0001F1F6", "\U0001F1F7"]
    liste_lettres = list(ascii_uppercase)
    liste_jours: dict = dict()
    step: int = 0

    # on itère à travers les jours
    for day in range(1, nb_jours+1, 1):
        future = datetime.today() + timedelta(days=day+decalage)
        horaire: str | list = ["Rassemblement **9h45**, début 10h !", "Rassemblement **13h45**, début 14h !", "Rassemblement **20h45**, début 21h !"] if future.weekday(
        ) >= 5 else "Rassemblement **20h45**, début 21h !"
        if isinstance(horaire, list):
            for h in horaire:
                liste_jours[f"{list_letters[step]} - {list_days[future.weekday()]} {future.day}.{future.month}"] = h
                step += 1
        else:
            liste_jours[f"{list_letters[step]} - {list_days[future.weekday()]} {future.day}.{future.month}"] = horaire
            step += 1

    emoji_deny = interactions.Emoji(
        name="patounes_no",
        id=979517886961967165
    )

    emoji_validation = interactions.Emoji(
        name="patounes_yes",
        id=979516938231361646
    )
    # on définit une lise d'emoji de la longueur du nombre de réponses possibles
    list_emoji: list = [list_letters[i]
                        for i in range(step)] + [emoji_validation] + [emoji_deny]

    # role = await interactions.get(bot, interactions.Role, object_id=ROLE_ID, parent_id=GUILD_ID) ajouter à embed.description les rôles à tag , avec champ de liste ?
    if mentions is not None:
        embed = interactions.Embed(
            title=titre, description=mentions, color=0xC2E9AA)
    else:
        embed = interactions.Embed(
            title=titre, color=0xC2E9AA)

    for key, value in liste_jours.items():
        embed.add_field(name=f"{key}", value=f"{value}", inline=False)

    information: str = f"Merci de répondre au plus vite !\nAprès avoir voté, cliquez sur {emoji_validation}\nSi aucune date ne vous convient, cliquez sur {emoji_deny}"

    message = await ctx.send(information, embeds=embed)
    # affiche les réactions pour le sondage
    for emoji in list_emoji:
        await message.create_reaction(emoji)


@ bot.command(
    name="poll",
    description="Crée un sondage simple à deux options",
    scope=guild_id,
    options=[
        interactions.Option(
            name="titre",
            description="Texte de titre du sondage.",
            type=interactions.OptionType.STRING,
            required=True,
        ),
        interactions.Option(
            name="mentions",
            description="Petit texte en-dessous pour mentionner des rôles, ou donner des détails.",
            type=interactions.OptionType.STRING,
            required=False,
        ),
    ],
)
async def poll(ctx: interactions.CommandContext, titre: str, mentions: str | None = None) -> None:
    patounes_tongue = interactions.Emoji(
        name="patounes_tongue",
        id=979488514561421332
    )
    emoji_deny = interactions.Emoji(
        name="patounes_no",
        id=979517886961967165
    )

    emoji_validation = interactions.Emoji(
        name="patounes_yes",
        id=979516938231361646
    )
    list_emoji: list = [emoji_validation, emoji_deny]

    if mentions is not None:
        embed = interactions.Embed(
            title=titre, description=mentions, color=0xC2E9AA)
    else:
        embed = interactions.Embed(
            title=titre, color=0xC2E9AA)

    poll_embed = {f'{emoji_validation} - Je suis intéressé.e !': "La date sera déterminée ultérieurement",
                  f'{emoji_deny} - Je ne souhaite pas participer': "Merci de cliquer pour montrer que vous avez lu"}

    for key, value in poll_embed.items():
        embed.add_field(name=f"{key}", value=f"{value}", inline=False)

    information: str = f"Merci de répondre au plus vite ! {patounes_tongue}"

    message = await ctx.send(information, embeds=embed)
    # affiche les réactions pour le sondage
    for emoji in list_emoji:
        await message.create_reaction(emoji)


def main() -> NoReturn:
    "Main loop for Grifouille"
    bot.load('interactions.ext.files')
    while (True):
        try:
            bot.start()
        except KeyboardInterrupt:
            print(KeyboardInterrupt("Keyboard interrupt, terminating Grifouille"))
            exit(0)
        except Exception as exc:
            print(exc)
            sleep(10)


if __name__ == "__main__":
    main()
