import time
import random
import asyncio
import Sensors
import numpy as np
from collections import Counter


class Goal:
    """
    Base class for all actions
    """
    a_agent = None

    def __init__(self, a_agent):
        self.a_agent = a_agent
        self.rc_sensor = a_agent.rc_sensor
        self.i_state = a_agent.i_state

        self.prev_currentActions = []
        self.requested_actions = []

    def requested(self, action):
        """
        Checks if the action is already requested
        :return: number of pending request for that action
        """
        return self.requested_actions.count(action)

    def executing(self, action):
        """
        Checks if the action is already executing
        :return: bool
        """
        if action in self.i_state.currentActions:
            return True
        else:
            return False

    def update_req_actions(self):
        """
        Takes the list i_state.currentActions and finds which actions have been added
        with respect prev_currentActions. Then updates the requested_actions list
        accordingly
        :return:
        """
        counter_prev = Counter(self.prev_currentActions)
        counter = Counter(self.i_state.currentActions)

        # New actions executing that were not executing before
        new_actions_executing = list((counter - counter_prev).elements())
        counter_new_actions = Counter(new_actions_executing)
        counter_req_actions = Counter(self.requested_actions)

        # Remove the new actions from the requested_actions list
        # Remove elements in counter_req_actions that are also in counter_new_actions
        for element, count in counter_new_actions.items():
            counter_req_actions[element] -= min(count, counter_req_actions[element])
        # Reconstruct the modified list counter_req_actions
        modified_req_actions = []
        for element, count in counter_req_actions.items():
            modified_req_actions.extend([element] * count)

        self.requested_actions = modified_req_actions

    async def update(self):
        # update requested actions
        self.update_req_actions()
        self.prev_currentActions = self.i_state.currentActions


class DoNothing(Goal):
    """
    Does nothing
    """
    def __init__(self, a_agent):
        super().__init__(a_agent)

    async def update(self):
        await super().update()
        print("Doing nothing")
        await asyncio.sleep(1)


class ForwardStop(Goal):
    """
    Moves forward till it detects an obstacle and then stops
    """
    STOPPED = 0
    MOVING = 1
    END = 2

    state = STOPPED

    def __init__(self, a_agent):
        super().__init__(a_agent)

    async def update(self):
        await super().update()
        if self.state == self.STOPPED:
            # If we are not moving, start moving
            self.requested_actions.append("W")
            await self.a_agent.send_message("action", "W")
            self.state = self.MOVING
            print("MOVING")
        elif self.state == self.MOVING:
            # If we are moving, check if we detect a wall
            sensor_hit = self.rc_sensor.sensor_rays[Sensors.RayCastSensor.HIT]
            print(sensor_hit)
            if any(ray_hit == 1 for ray_hit in self.rc_sensor.sensor_rays[Sensors.RayCastSensor.HIT]):
                self.requested_actions.append("S")
                await self.a_agent.send_message("action", "S")
                self.state = self.END
                print("END")
            else:
                await asyncio.sleep(0)
        elif self.state == self.END:
            # If we have finished, don't do anything else
            await asyncio.sleep(10)
            print("WAITING")
        else:
            print("Unknown state: " + str(self.state))


class Turn(Goal):
    """
    Repeats the action of turning a random number of degrees in a random
    direction (right or left)
    """
    STOPPED = 0
    TURNING = 1

    state = STOPPED

    def __init__(self, a_agent):
        super().__init__(a_agent)

    async def update(self):
        await super().update()

        if self.state == self.STOPPED: # while stopped
            DEG = random.randint(10, 360) # random number of degrees
            DIR = random.choice(["A", "D"]) # random direction
            DEG = 90
            print("TURNING " + DIR + " " + str(DEG) + " DEGREES") # shpw the action
            
            TURNS = self.round_angle(DEG) // 5 # translate degrees to turn iterations

            async for _ in self.async_generator(TURNS): # iterate through the turns
                self.requested_actions.append(DIR) # add the action to the requested actions
                await self.a_agent.send_message("action", DIR) # send the action to the agent
            
            self.state = self.TURNING # change the state to turning

        elif self.state == self.TURNING: # while turning
            if not self.executing("A") and not self.executing("D"): # if the agent is not turning
                print("STOPPED TURNING") # show that the agent has stopped turning
                self.state = self.STOPPED # change the state to stopped
            else:
                await asyncio.sleep(0.5) # wait for a short time
            
    # Asynchronous generator function
    async def async_generator(self, n):
        for _ in range(n): 
            await asyncio.sleep(0.25) # wait for a short time
            yield _ # return the current iteration

    def round_angle(self, angle):
        """
        Rounds the angle to the nearest multiple of 5,
        rounding up if it is near to the top and rounding down if it is near to the bottom.
        """
        remainder = angle % 5

        if remainder >= 2.5:
            rounded_angle = angle + (5 - remainder)  # Round up
        else:
            rounded_angle = angle - remainder  # Round down

        return rounded_angle


class RandomRoam(Goal):
    """
    Moves around following a direction for a while, changes direction,
    decides to stop, moves again, etc.
    All of this following certain probabilities and maintaining the action during
    a pre-defined amount of time.
    """

    IDLE = -1
    STOPPED = 0
    MOVING = 1
    TURNING = 2

    state = IDLE    

    
    act = {0 : 0.25,
           1 : 0.40,
           2 : 0.35 }

    def __init__(self, a_agent):
        super().__init__(a_agent)

    async def update(self):
        await super().update()

        if self.state == self.IDLE:
            self.state = self.choose_from_dict(self.act)

        elif self.state == self.STOPPED:
            SEC = self.choose_from_list_gaussian([num for num in range(1, 7)])
            print("WAITING " + str(SEC) + " SECONDS")

            await asyncio.sleep(SEC)

            self.state = self.choose_from_dict(self.act)
    
        elif self.state == self.MOVING:
            SEC = self.choose_from_list_gaussian([num for num in range(3, 11)])
            print("MOVING " + str(SEC) + " SECONDS")

            self.requested_actions.append("W")
            await self.a_agent.send_message("action", "W")
            # await asyncio.sleep(SEC)

            start_time = time.time()
            while time.time() - start_time < SEC:
            # If we are moving, check if we detect a wall
                sensor_hit = self.rc_sensor.sensor_rays[Sensors.RayCastSensor.HIT]
                if any(ray_hit == 1 for ray_hit in self.rc_sensor.sensor_rays[Sensors.RayCastSensor.HIT]):
                    break
                await asyncio.sleep(0.1)

            self.requested_actions.append("S")
            await self.a_agent.send_message("action", "S")
            await asyncio.sleep(1)

            self.state = self.choose_from_dict(self.act)

        elif self.state == self.TURNING:
            DEG = self.choose_from_list_gaussian([num for num in range(10, 360)], mean=35)
            DIR = self.choose_from_list_gaussian(["A", "D"])
            
            TURNS = self.round_angle(DEG) // 5
            print("TURNING " + DIR + " " + str(DEG) + " DEGREES")
            async for _ in self.async_generator(TURNS):
                self.requested_actions.append(DIR)
                await self.a_agent.send_message("action", DIR)
            
            await asyncio.sleep(1)

            self.state = self.choose_from_dict(self.act)

        else:
            print("Unknown state: " + str(self.state))

    def round_angle(self, angle):
        """
        Rounds the angle to the nearest multiple of 5,
        rounding up if it is near to the top and rounding down if it is near to the bottom.
        """
        remainder = angle % 5

        if remainder >= 2.5:
            rounded_angle = angle + (5 - remainder)  # Round up
        else:
            rounded_angle = angle - remainder  # Round down

        return rounded_angle

    def choose_from_list_gaussian(self, my_list, mean=None, std_dev=None):
        if mean is None:
            mean = len(my_list) / 2  # Default: center of the list
        if std_dev is None:
            std_dev = len(my_list) / 4  # Default: spread over the list
        
        # Generate a random index using the Gaussian distribution
        index = int(np.random.normal(mean, std_dev))
        
        # Clip the index to the valid range
        index = max(min(index, len(my_list) - 1), 0)
        
        return my_list[index]

    def choose_from_dict(self, my_dict):
        options = list(my_dict.keys())
        weights = list(my_dict.values())
        return random.choices(options, weights=weights)[0]

    async def async_generator(self, n):
        for _ in range(n): 
            await asyncio.sleep(0.25) # wait for a short time
            yield _ # return the current iteration


class Avoid(Goal):
    """
    Moves always forward avoiding obstacles
    """
    IDLE = 0
    MOVING = 1
    TURNING = 2

    state = IDLE

    OBSTACLE_DIR = None

    def __init__(self, a_agent):
        super().__init__(a_agent)

    async def update(self):
        await super().update()
        
        # BEGIN STATE
        if self.state == self.IDLE:
            self.state = self.MOVING

        # AGENT IS IN MOVING STATE
        elif self.state == self.MOVING:

            # START MOVING
            self.requested_actions.append("W")
            await self.a_agent.send_message("action", "W")

            # CHECK IF THERE IS AN OBSTACLE
            sensor_hit = self.rc_sensor.sensor_rays[Sensors.RayCastSensor.HIT]
            if any(ray_hit == 1 for ray_hit in self.rc_sensor.sensor_rays[Sensors.RayCastSensor.HIT]):
                self.requested_actions.append("S")
                await self.a_agent.send_message("action", "S")

                print("Obstacle detected")
                # FIND OBSTACLE DIRECTION
                if sensor_hit[0] == 1:
                    self.OBSTACLE_DIR = "D"
                elif sensor_hit[2] == 1:
                    self.OBSTACLE_DIR = "A"
                else:
                    self.OBSTACLE_DIR = random.choice(["A", "D"])

                self.state = self.TURNING
                
            await asyncio.sleep(0.1)

        elif self.state == self.TURNING:
            DIR = self.OBSTACLE_DIR # opposite direction of obstacle
            DEG = random.choice([deg for deg in range(20, 60, 5)])
            TURNS = DEG // 5
            print("SURROUNDING OBSTACLE")
            
            # TURN 45 DEGREES
            async for _ in self.async_generator(TURNS):
                self.requested_actions.append(DIR)
                await self.a_agent.send_message("action", DIR)
            
            await asyncio.sleep(1)

            self.state = self.MOVING
            
    async def async_generator(self, n):
        for _ in range(n): 
            await asyncio.sleep(0.25) # wait for a short time
            yield _ # return the current iteration