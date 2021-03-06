# Runs a Kalman filter to fuse sensor data
# Data must have fields:
# %time,field.O_x,field.O_y,field.O_t,field.I_t,field.Co_I_t,field.G_x,field.G_y,field.Co_gps_x,field.Co_gps_y

import sys
import csv
import argparse

import numpy as np
import matplotlib.pyplot as plt

class Kalman_filter:

	# Constructor
	# Sets the expected fields for the data file
	#
	# file_name : string
	# The name of the data file to be loaded
	#
	# process_noise_val : float
	# This will be set as the static noise for the state update
	#
	# measurement_error_val : float
	# This will be set as the static covariance matrix for the measurement model
	#
	# previous_cov_val : float
	# This will initialize the covariance of the starting state
	#
	# gps_cov_override : tuple : (cov_x, cov_y)
	# If set, this will override the covariance set for gps in the file and replace them with the sent value
	#
	# imu_cov_override : tuple : (cov_t,)
	# If set, this will override the covariance set for the imu in the file and replace them with the sent value
	#
	# gps_noise : float
	# If set, noise will be added to the gps_data with the sent value as the sigma of the noise 
	def __init__(self, file_name, process_noise_val=.0001, measurement_cov_val=.01, previous_cov_val=.01, gps_cov_override=None, imu_cov_override=None, gps_noise=None):

		# Set the wheel distance
		self.wheel_distance = 1

		# Set the value of delta t
		self.delta_t = .001

		# Set the value of the velocity
		self.velocity = .14

		# Set the value of the input_effect
		self.input_effect = np.identity(5)

		# Set the control_input
		self.control_input = np.matrix(np.array([[0],[0],[0],[0],[0]]))

		# Set the process noise to be a static matrix with the given configuration
		self.process_noise = np.identity(5) * process_noise_val

		# Set the measurement_matrix
		self.measurement_effect = np.identity(5)

		# Set the initial covariance matrix to the given number
		self.measurement_cov = np.identity(5) * measurement_cov_val

		# Set the covariance of the initial "previous" step
		self.previous_cov = np.identity(5) * previous_cov_val

		# Time field
		self.time_index = "%time"

		# Odometer. Has X, Y, and Orientation
		self.odometer_x = "field.O_x"
		self.odometer_y = "field.O_y"
		self.odometer_theta = "field.O_t"

		# IMU. Has theta
		self.imu_theta = "field.I_t"

		# IMU covariance. Comes from the data file
		self.imu_cov_theta = "field.Co_I_t"

		# GPS. Has X, Y
		self.gps_x = "field.G_x"
		self.gps_y = "field.G_y"

		# GPS covariance
		self.gps_cov_x = "field.Co_gps_x"
		self.gps_cov_y = "field.Co_gps_y"

		# The matrices will hold all of the data
		self.time = None
		self.odometry = None
		self.imu = None
		self.imu_cov = None
		self.gps = None
		self.gps_cov = None

		# Load all of the data
		self.get_data(file_name)

		# If gps_cov_override is set, do the override
		if gps_cov_override:

			self.override_cov(self.gps_cov, gps_cov_override)

		# If imu_cov_override, do the override
		if imu_cov_override:

			self.override_cov(self.imu_cov, imu_cov_override)

		# If gps_noise is sent, add the specified noise
		if gps_noise is not None:

			self.noise_gps(gps_noise)

		# This will hold the predictions as the filter runs
		# x, y, velocity, heading, omega
		self.state = [np.matrix([[0],[0],[0],[0],[0]], dtype=np.float32).transpose()]

	# Loads all of the data into a numpy arrays from a csv file
	# Places all of the data into the arrays as specified above
	#
	# file_name : string
	# The name including path of the file to be loaded
	def get_data(self, file_name):

		# Open the data file
		with open(file_name) as data_file:

			# Get the csv reader
			data_reader = csv.DictReader(data_file)

			# Lists will temporarily hold the data
			list_time = []
			list_odometry = []
			list_imu = []
			list_imu_cov = []
			list_gps = []
			list_gps_cov = []

			# Go through each line in the file
			for line in data_reader:

				# Time stamp
				list_time.append(np.array([float(line[self.time_index])]))

				# Odometry
				list_odometry.append(np.array([float(line[self.odometer_x]), float(line[self.odometer_y]), float(line[self.odometer_theta])]))

				# IMU
				list_imu.append(np.array([float(line[self.imu_theta])]))

				# IMU cov
				list_imu_cov.append(np.array([float(line[self.imu_cov_theta])]))

				# GPS
				list_gps.append(np.array([float(line[self.gps_x]),float(line[self.gps_y])]))

				# GPS cov
				list_gps_cov.append(np.array([float(line[self.gps_cov_x]),float(line[self.gps_cov_y])]))

		# Convert all of the lists into matrices
		self.time = np.matrix(list_time)
		self.odometry = np.matrix(list_odometry)
		self.imu = np.matrix(list_imu)
		self.imu_cov = np.matrix(list_imu_cov)
		self.gps = np.matrix(list_gps)
		self.gps_cov = np.matrix(list_gps_cov)

	# Overrides the covariance and sets them all to the sent value
	#
	# to_override : np.array
	# The covariances being overridden
	#
	# override_value : tuple
	# The values to set as the new covariance, number of values must be equal to the second dimension in to_override
	def override_cov(self, to_override, override_value):

		# Go through the items in the override_value
		for index, value in enumerate(override_value):

			# Set all values in the covariance array
			to_override[:, index] = value

	# Adds gaussian noise to the GPS data
	#
	# sigma : float
	# The sigma value to use for the gaussian noise
	def noise_gps(self, sigma):

		# Create the noise matrix
		noise = np.random.normal(scale=sigma, size=self.gps.shape)

		# Add the noise to the data
		self.gps += noise

	# Fuses two gaussian sensor readings
	#
	# first_mean
	# The value of the first sensor
	#
	# second_mean
	# The value of the second sensor
	#
	# first_deviation
	# The noise of the first sensor
	#
	# second_deviation
	# The noise of the second sensor
	#
	# returns the mean, deviation
	def fuse(self, first_mean, second_mean, first_deviation, second_deviation):

		# Set the mean value
		mean = (first_mean/max(first_deviation ** 2, np.finfo(np.float32).eps) + second_mean/max(second_deviation ** 2, np.finfo(np.float32).eps))/(1/max(first_deviation ** 2, np.finfo(np.float32).eps) + 1/max(second_deviation ** 2, np.finfo(np.float32).eps))

		# Set the deviation
		deviation = (1/max(first_deviation ** 2, np.finfo(np.float32).eps) + 1/max(second_deviation ** 2, np.finfo(np.float32).eps)) ** (-.5)

		return mean, deviation

	# Fuses the sensor readings into one vector and returns it
	#
	# index : int
	# time to load the data from
	#
	# returns: mean, variance : (1,5), (5,5)
	def fuse_readings(self, index):

		# Get the blank mean matrix
		mean = np.matrix(np.zeros(5))

		# Get the blank deviation matrix
		deviation = np.identity(5)

		# Set the mean and deviation for x using odometry and GPS
		mean[0, 0], deviation[0, 0] = self.fuse(self.odometry[index, 0], self.gps[index, 0], self.measurement_cov[0, 0], self.gps_cov[index, 0])

		# Set the mean and deviation for y using odometry and GPS
		mean[0, 1], deviation[1, 1] = self.fuse(self.odometry[index, 1], self.gps[index, 1], self.measurement_cov[1, 1], self.gps_cov[index, 1])

		# Set the value for velocity
		mean[0,2] = self.velocity

		# Set the variance for velocity
		deviation[2, 2] = self.measurement_cov[2, 2]

		# Set the mean and deviation for theta using odometry and IMU
		mean[0, 3], deviation[3, 3] = self.fuse(self.odometry[index, 2], self.imu[index, 0], self.measurement_cov[2, 2], self.imu_cov[index, 0])

		# Set the value for omega
		mean[0,4] = self.velocity*np.tan(np.radians(self.odometry[index, 2])) / self.wheel_distance

		# Set the variance for omega
		deviation[4, 4] = self.measurement_cov[4, 4]

		return mean.transpose(), deviation

	# Predicts the updated state from the previous state and the ideal model
	def model_predict(self, index):

		# Set the transition matrix
		transition_matrix = np.matrix([[1,0,self.delta_t*np.cos(np.radians(self.odometry[index, 2])),0,0],[0,1,self.delta_t*np.cos(np.radians(self.odometry[index, 2])),0,0],[0,0,1,0,0],[0,0,0,1,self.delta_t],[0,0,0,0,1]])

		# Update the cov
		self.previous_cov = np.dot(transition_matrix, np.dot(self.previous_cov, transition_matrix.transpose())) + self.process_noise

		# Calculate the updated state prediction
		return np.dot(transition_matrix, self.state[-1].transpose()) + np.dot(self.input_effect, self.control_input)

	# Updates the state
	#
	# model_prediction : np.matrix : shape (1,5)
	def state_update(self, index):

		# Get the model predicted state
		predicted_state = self.model_predict(index)

		# Get the sensor readings at this step
		(measurement_readings, measurement_variance) = self.fuse_readings(index)

		# Get the mean of the predicted distribution of the measurement vector
		predicted_distribution_Y = np.dot(self.measurement_effect, predicted_state)

		# Get the covariance of Y
		cov_Y = self.measurement_cov + np.dot(self.measurement_effect, np.dot(self.previous_cov, self.measurement_effect.transpose()))

		# Get the Kalman Gain
		kalman_gain = np.dot(self.previous_cov, np.dot(self.measurement_effect.transpose(), np.linalg.inv(cov_Y)))

		# Update the state
		self.state.append((predicted_state + np.dot(kalman_gain, (measurement_readings - predicted_distribution_Y))).transpose())

		# Update the previous_cov with the new value
		self.previous_cov = self.previous_cov - np.dot(kalman_gain, np.dot(cov_Y, kalman_gain.transpose()))

	# Runs the Kalman filter on the given data
	def run(self):

		# Go through each data point and run the kalman filter on it
		for index in range(len(self.time)):

			# Update the state
			self.state_update(index)

	# Shows the raw gps data and the predicted path
	# GPS is shown as red dots
	# Odometry is shown as green x's
	# Kalman output is shown as a blue line
	def show_plot(self):

		# Figure 1 will be the location
		plt.figure(1)

		# Set the title of the graph
		plt.title("Position")

		# Set the x and y axis names
		plt.xlabel("X location")
		plt.ylabel("Y location")

		# Add the gps data to the graph as red dots
		plt.plot(self.gps[:, 0], self.gps[:, 1], 'ro', label="GPS")

		# Add the odometry data to the graph as green x's
		plt.plot(self.odometry[:, 0], self.odometry[:, 1], 'gx', label="Odometry")

		# Add the kalman filter location output to the graph as a blue line
		x_state = []
		y_state = []
		for item in self.state:
			x_state.append(item[0,0])
			y_state.append(item[0,1])
		plt.plot(x_state, y_state, 'b-', label="Kalman Filter Output")

		# Set the legend
		plt.legend(loc="best")

		# Figure 2 will be the heading
		plt.figure(2)

		# Set the title
		plt.title("Heading")

		# Set the x and y axis names
		plt.xlabel("Time")
		plt.ylabel("Heading")

		# Add the IMU data to the graph as red dots
		plt.plot(range(len(self.imu)), self.imu[:, 0], 'ro', label="IMU")

		# Add the odometry data as green x's
		plt.plot(range(len(self.odometry)), self.odometry[:, 2], 'gx', label="Odometry")

		# Add the kalman filter heading output as a blue line
		heading_state = []
		for item in self.state:
			heading_state.append(item[0,3])
		plt.plot(range(len(heading_state)), heading_state, 'b-',  label="Kalman Filter Output")

		# Set the legend
		plt.legend(loc="best")

		# Show the graph
		plt.show()

# If this is run as main, run the filter on the given configuration file
if __name__ == "__main__":

	# Create the parser to get arguments
	parser = argparse.ArgumentParser(description='Runs a Kalman Filter')

	# Add the load name
	parser.add_argument("file_name", help="The name of the file containing the sensor data")

	# Get the arguments
	args = parser.parse_args()

	# Create the Kalman Filter, this one won't have any modifications
	K_filter_normal = Kalman_filter(args.file_name)

	# Run the filter
	K_filter_normal.run()

	# Show the data
	print "\n\nResults without any changes to covariance or data"
	print "Exit both windows to continue\n\n"
	K_filter_normal.show_plot()

	# Create a Kalman filter with different GPS covariance
	K_filter_gps_cov = Kalman_filter(args.file_name, gps_cov_override=(.01, .01))

	# Run the filter
	K_filter_gps_cov.run()

	# Show the data
	print "\n\nResults with GPS covariance set to: ", .01, " ", .01
	print "Exit both windows to continue\n\n"
	K_filter_gps_cov.show_plot()

	# Create a Kalman filter with different IMU covariance
	K_filter_imu_cov = Kalman_filter(args.file_name, imu_cov_override=(.1,))

	# Run the filter
	K_filter_imu_cov.run()

	# Show the data
	print "\n\nResults with IMU covariance set to: ", .1
	print "Exit both windows to continue\n\n"
	K_filter_imu_cov.show_plot()

	# Create a Kalman filter with different GPS covariance and add noise to the GPS data
	K_filter_gps_noise = Kalman_filter(args.file_name, gps_cov_override=(.000001, .000001), gps_noise=1)

	# Run the filter
	K_filter_gps_noise.run()

	# Show the data
	print "\n\nResults with GPS covariance set to: ", .000001, " ", .000001
	print "Noise added to GPS data with sigma: ", 1
	print "Exit both windows to continue\n\n"
	K_filter_gps_noise.show_plot()
