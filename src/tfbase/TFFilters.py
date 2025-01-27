"""TFFilters module: contains various physics query filters"""

from panda3d.pphysics import PythonPhysQueryFilter, PhysRayCastResult, PhysSweepResult
from panda3d.core import NodePath, PStatCollector, Point3, Vec3

from tf.tfbase.TFGlobals import Contents

tf_filter_coll = PStatCollector("App:TFFilterQuery:DoFilter")
tf_filter_pytag_coll = PStatCollector("App:TFFilterQuery:DoFilter:GetPythonTag")

ENTITY_TAG = "entity"

def hitBoxes(actor, mask, entity, source):
    """
    If the given entity has hitboxes and the mask contains the Contents.HitBox
    bit, ignores the entity's collision hull and only checks against the hit
    boxes.
    """

    contents = actor.getContentsMask().getWord()
    if (mask & Contents.HitBox) == 0:
        # Not checking against hitboxes, ignore hitboxes.
        if (contents & Contents.HitBox) != 0:
            return 0
    else:
        # We are checking against hitboxes.  Ignore the collision hull, unless
        # the entity doesn't actually have hitboxes.
        if len(entity.hitBoxes) > 0:
            # The entity has hitboxes, so ignore anything that isn't a hitbox.
            if (contents & Contents.HitBox) == 0:
                # This isn't a hitbox.
                return 0

    return 1

def ignorePlayers(actor, mask, entity, source):
    """
    Ignores actors that are attached to players.
    """
    if entity.isPlayer():
        return 0
    return 1

def ignoreEnemies(actor, mask, entity, source):
    """
    Ignores entities that are on the opposite team of the source, including
    buildings.
    """
    if entity.team != source.team:
        return 0
    return 1

def ignoreEnemyPlayers(actor, mask, entity, source):
    """
    Ignores players on the opposite team as the source.  Does not ignore
    enemy buildings.
    """
    if (entity.team != source.team) and entity.isPlayer():
        return 0
    return 1

def ignoreEnemyBuildings(actor, mask, entity, source):
    """
    Ignores enemy buildings, but not players.
    """
    if (entity.team != source.team) and entity.isObject():
        return 0
    return 1

def ignoreTeammates(actor, mask, entity, source):
    """
    Ignores entities that are on the same team as the player/source, including
    buildings.
    """
    if entity.team == source.team:
        return 0
    return 1

def ignoreTeammatePlayers(actor, mask, entity, source):
    """
    Ignores other players that are on the same team as the source.
    Does not ignore buildings and other entities.
    """
    if (entity.team == source.team) and entity.isPlayer():
        return 0
    return 1

def ignoreTeammateBuildings(actor, mask, entity, source):
    """
    Ignores only friendly buildings.
    """
    if (entity.team == source.team) and entity.isObject():
        return 0
    return 1

def ignoreSelf(actor, mask, entity, source):
    """
    Ignores the source entity of the query.
    """
    if entity == source:
        return 0
    return 1

class TFQueryFilter(PythonPhysQueryFilter):

    def __init__(self, sourceEntity = None, filters = [], ignoreSource = True):
        PythonPhysQueryFilter.__init__(self, self.doFilter)
        self.sourceEntity = sourceEntity
        self.ignoreSource = ignoreSource
        self.filters = filters

    def doFilter(self, actor, mask, collisionGroup, hitType):
        """
        Runs the set of Python filters in order.  The filter will early-out
        if one of the filters ignores the query.

        TODO: Move this to C++ if it's too slow.
        """

        entity = actor.getPythonTag(ENTITY_TAG)
        if not entity:
            # It must be associated with an entity.
            return 0

        if self.ignoreSource and entity == self.sourceEntity:
            # Ignore ourselves.
            return 0

        if not hitBoxes(actor, mask, entity, self.sourceEntity):
            return 0

        if not entity.shouldCollide(collisionGroup, mask):
            # Entity doesn't collide with this.
            return 0

        for f in self.filters:
            retVal = f(actor, mask, entity, self.sourceEntity)
            if not retVal:
                return 0

        return hitType

def traceLine(start, end, contents, cgroup, filter):
    result = PhysRayCastResult()
    dir = end - start
    dist = dir.length()
    dir.normalize()
    base.physicsWorld.raycast(result, start, dir, dist, contents, 0, cgroup, filter)
    data = {}
    data['hit'] = result.hasBlock()
    if result.hasBlock():
        block = result.getBlock()
        actor = block.getActor()
        data['actor'] = actor
        data['pos'] = block.getPosition()
        data['norm'] = block.getNormal()
        data['mat'] = block.getMaterial()
        data['ent'] = actor.getPythonTag('entity') if actor else None
    else:
        data['actor'] = None
        data['pos'] = Point3()
        data['norm'] = Vec3()
        data['mat'] = None
        data['ent'] = None
    return data

def traceBox(mins, maxs, dir, dist, contents, cgroup, filter):
    result = PhysSweepResult()
    base.physicsWorld.boxcast(result, mins, maxs, dir, dist,
                              0, contents, 0, cgroup, filter)
    data = {}
    data['hit'] = result.hasBlock()
    if result.hasBlock():
        block = result.getBlock()
        actor = block.getActor()
        data['actor'] = actor
        data['pos'] = block.getPosition()
        data['norm'] = block.getNormal()
        data['mat'] = block.getMaterial()
        data['ent'] = actor.getPythonTag('entity') if actor else None
    else:
        data['actor'] = None
        data['pos'] = Point3()
        data['norm'] = Vec3()
        data['mat'] = None
        data['ent'] = None
    return data
