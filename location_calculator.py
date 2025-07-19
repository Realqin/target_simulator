# -*- coding: utf-8 -*-

import math

class LocationCalculator:
    """
    根据起点、速度、航向和时间计算下一个经纬度坐标。
    """
    def __init__(self, start_lat, start_lon, speed_knots, course_degrees):
        """
        初始化计算器。

        :param start_lat: 起始纬度 (度)
        :param start_lon: 起始经度 (度)
        :param speed_knots: 速度 (节)
        :param course_degrees: 航向 (度, 0-360)
        """
        self.current_lat = float(start_lat)
        self.current_lon = float(start_lon)
        self.speed_knots = float(speed_knots)
        self.course_degrees = float(course_degrees)
        
        # 地球平均半径，单位：米
        self.EARTH_RADIUS_METERS = 6371000

    def calculate_next_point(self, time_interval_seconds):
        """
        计算下一个时间点的经纬度。

        :param time_interval_seconds: 时间间隔 (秒)
        :return: (新的纬度, 新的经度) 元组
        """
        # 1. 将速度从节转换为米/秒 (1节 ≈ 0.514444 米/秒)
        speed_mps = self.speed_knots * 0.514444

        # 2. 计算距离 (米)
        distance_meters = speed_mps * time_interval_seconds

        # 3. 将航向从度转换为弧度
        course_rad = math.radians(self.course_degrees)

        # 4. 将当前经纬度从度转换为弧度
        lat_rad = math.radians(self.current_lat)
        lon_rad = math.radians(self.current_lon)

        # 5. 使用球面航位推算公式计算新位置
        # 参考: https://www.movable-type.co.uk/scripts/latlong.html (Destination point given distance and bearing from start point)
        
        angular_distance = distance_meters / self.EARTH_RADIUS_METERS

        new_lat_rad = math.asin(
            math.sin(lat_rad) * math.cos(angular_distance) +
            math.cos(lat_rad) * math.sin(angular_distance) * math.cos(course_rad)
        )

        new_lon_rad = lon_rad + math.atan2(
            math.sin(course_rad) * math.sin(angular_distance) * math.cos(lat_rad),
            math.cos(angular_distance) - math.sin(lat_rad) * math.sin(new_lat_rad)
        )

        # 6. 将新经纬度从弧度转换回度
        new_lat = math.degrees(new_lat_rad)
        new_lon = math.degrees(new_lon_rad)

        # 7. 更新当前位置，为下一次计算做准备
        self.current_lat = new_lat
        self.current_lon = new_lon

        return new_lat, new_lon

    def update_params(self, speed_knots=None, course_degrees=None):
        """
        允许在计算过程中更新速度或航向。
        """
        if speed_knots is not None:
            self.speed_knots = float(speed_knots)
        if course_degrees is not None:
            self.course_degrees = float(course_degrees)

