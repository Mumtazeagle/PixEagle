#src/classes/px4_controller.py
import asyncio
import math
import logging
from mavsdk import System
from classes.parameters import Parameters
from mavsdk.offboard import OffboardError, VelocityNedYaw, VelocityBodyYawspeed
from classes.setpoint_handler import SetpointHandler

# Configure logging
logger = logging.getLogger(__name__)

class PX4Controller:
    def __init__(self):
        if Parameters.EXTERNAL_MAVSDK_SERVER:
            self.drone = System(mavsdk_server_address='localhost', port=50051)
        else:
            self.drone = System()
        self.current_yaw = 0.0  # Current yaw in radians
        self.current_pitch = 0.0  # Current pitch in radians
        self.current_roll = 0.0  # Current roll in radians
        self.current_altitude = 0.0  # Current altitude in meters
        self.camera_yaw_offset = Parameters.CAMERA_YAW_OFFSET
        self.update_task = None  # Task for telemetry updates
        self.setpoint_handler = SetpointHandler(Parameters.FOLLOWER_MODE.capitalize().replace("_", " "))  # Use the mode from Parameters
        self.active_mode = False
        
    async def connect(self):
        """Connects to the drone using the system address from Parameters."""
        await self.drone.connect(system_address=Parameters.SYSTEM_ADDRESS)
        self.active_mode = True
        logger.info("Connected to the drone.")
        self.update_task = asyncio.create_task(self.update_drone_data())

    async def update_drone_data(self):
        """Continuously updates current yaw, pitch, roll, and altitude."""
        while self.active_mode:
            try:
                async for position in self.drone.telemetry.position():
                    self.current_altitude = position.relative_altitude_m
                async for attitude in self.drone.telemetry.attitude_euler():
                    self.current_yaw = attitude.yaw + self.camera_yaw_offset
                    self.current_pitch = attitude.pitch  # Updating the pitch
                    self.current_roll = attitude.roll  # Updating the roll
            except asyncio.CancelledError:
                logger.warning("Telemetry update task was cancelled.")
                break
            except Exception as e:
                logger.error(f"Error updating telemetry: {e}")
                await asyncio.sleep(1)  # Wait before retrying

    def get_orientation(self):
        """Returns the current orientation (yaw, pitch, roll) of the drone."""
        return self.current_yaw, self.current_pitch, self.current_roll

    async def send_ned_velocity_commands(self):
        """Sends velocity commands to the drone in offboard mode using the setpoints from the handler."""
        setpoints = self.setpoint_handler.get_fields()
        vel_x = setpoints.get('vel_x', 0)
        vel_y = setpoints.get('vel_y', 0)
        vel_z = setpoints.get('vel_z', 0)
        ned_vel_x, ned_vel_y = self.convert_to_ned(vel_x, vel_y, self.current_yaw)
        
        if Parameters.ENABLE_SETPOINT_DEBUGGING:
            logger.debug(f"sending NED velocity commands: Vx={ned_vel_x}, Vy={ned_vel_y}, Vz={vel_z}, Yaw={self.current_yaw}")
        
        try:
            next_setpoint = VelocityNedYaw(ned_vel_x, ned_vel_y, vel_z, self.current_yaw)
            await self.drone.offboard.set_velocity_ned(next_setpoint)
        except OffboardError as e:
            logger.error(f"Failed to send offboard command: {e}")

    async def send_body_velocity_commands(self):
        """Sends body frame velocity commands to the drone in offboard mode using the setpoints from the handler."""
        setpoints = self.setpoint_handler.get_fields()
        vx = setpoints.get('vel_x', 0)
        vy = setpoints.get('vel_y', 0)
        vz = setpoints.get('vel_z', 0)
        yaw_rate = setpoints.get('yaw_rate', 0)  # Use yaw_rate if available
        
        try:
            logger.debug(f"Setting VELOCITY_BODY setpoint: Vx={vx}, Vy={vy}, Vz={vz}, Yaw rate={yaw_rate}")
            next_setpoint = VelocityBodyYawspeed(vx, vy, vz, yaw_rate)
            await self.drone.offboard.set_velocity_body(next_setpoint)
        except OffboardError as e:
            logger.error(f"Failed to send offboard velocity command: {e}")

    def convert_to_ned(self, vel_x, vel_y, yaw):
        """Converts local frame velocities to NED frame using the current yaw."""
        ned_vel_x = vel_x * math.cos(yaw) - vel_y * math.sin(yaw)
        ned_vel_y = vel_x * math.sin(yaw) + vel_y * math.cos(yaw)
        return ned_vel_x, ned_vel_y

    async def start_offboard_mode(self):
        """
        Attempts to start offboard mode.

        Returns:
            dict: Details of the offboard mode attempt.
        """
        result = {"steps": [], "errors": []}
        try:
            await self.drone.offboard.start()
            result["steps"].append("Offboard mode started.")
            logger.info("Offboard mode started.")
        except Exception as e:
            result["errors"].append(f"Failed to start offboard mode: {e}")
            logger.error(f"Failed to start offboard mode: {e}")
        return result

    async def stop_offboard_mode(self):
        """Stops offboard mode."""
        logger.info("Stopping offboard mode...")
        await self.drone.offboard.stop()

    async def stop(self):
        """Stops all operations and disconnects from the drone."""
        if self.update_task:
            self.update_task.cancel()
            await self.update_task
        await self.stop_offboard_mode()
        self.active_mode = False
        logger.info("Disconnected from the drone.")

    async def send_initial_setpoint(self):
        """Sends an initial setpoint to enable offboard mode start."""
        await self.send_body_velocity_commands()

    def update_setpoint_handler_profile(self, profile_name: str):
        """Updates the setpoint handler profile based on the mission type."""
        self.setpoint_handler = SetpointHandler(profile_name)
        logger.info(f"SetpointHandler profile updated to: {profile_name}")
