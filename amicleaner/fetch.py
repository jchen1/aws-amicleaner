#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import absolute_import
from builtins import object
import boto3
from botocore.config import Config
from .resources.config import BOTO3_RETRIES
from .resources.models import AMI


class Fetcher(object):

    """ Fetches function for AMI candidates to deletion """

    def __init__(self, ec2=None, autoscaling=None):

        """ Initializes aws sdk clients """

        self.ec2 = ec2 or boto3.client('ec2', config=Config(retries={'max_attempts': BOTO3_RETRIES}))
        self.asg = autoscaling or boto3.client('autoscaling')

    def fetch_available_amis(self):

        """ Retrieve from your aws account your custom AMIs"""

        available_amis = dict()

        my_custom_images = self.ec2.describe_images(Owners=['self'])
        for image_json in my_custom_images.get('Images'):
            ami = AMI.object_with_json(image_json)
            available_amis[ami.id] = ami

        return available_amis

    def fetch_attached_lc(self):

        """
        Find AMIs for launch configurations attached
        to autoscaling groups
        """

        resp = self.asg.describe_auto_scaling_groups()
        used_lc = [lc for asg in resp.get("AutoScalingGroups", []) 
                      for lc in [asg.get("LaunchConfigurationName", "")] if len(lc) > 0]

        resp = self.asg.describe_launch_configurations(
            LaunchConfigurationNames=used_lc
        )
        amis = [lc.get("ImageId")
                for lc in resp.get("LaunchConfigurations", [])]

        return amis

    def fetch_attached_lt(self):

        """
        Find AMIs for launch templates attached
        to autoscaling groups
        """

        resp = self.asg.describe_auto_scaling_groups()

        used_lt = [lt for asg in resp.get("AutoScalingGroups", []) 
                      for lt in [asg.get("LaunchTemplate", {}).get("LaunchTemplateName", ""), 
                                 asg.get("MixedInstancesPolicy", {}).get("LaunchTemplate", {}).get("LaunchTemplateSpecification", {}).get("LaunchTemplateName", "")]
                      if len(lt) > 0]

        amis = []
        for lt_name in used_lt:
            resp = self.ec2.describe_launch_template_versions(
                LaunchTemplateName=lt_name
            )
            all_lt_versions = sorted(resp.get("LaunchTemplateVersions", []), key=lambda lt: lt.get("VersionNumber", -1))
            lt_latest_version = all_lt_versions[-1]
            lt_default_version = [lt for lt in all_lt_versions if lt.get("DefaultVersion", False) == True][0]

            amis.append(lt_latest_version.get("LaunchTemplateData", {}).get("ImageId"))
            amis.append(lt_default_version.get("LaunchTemplateData", {}).get("ImageId"))

        return amis

    def fetch_zeroed_asg_lc(self):

        """
        Find AMIs for autoscaling groups who's desired capacity is set to 0
        """

        resp = self.asg.describe_auto_scaling_groups()
        zeroed_lcs = [asg.get("LaunchConfigurationName", "")
                      for asg in resp.get("AutoScalingGroups", [])
                      if asg.get("DesiredCapacity", 0) == 0 and len(asg.get("LaunchConfigurationNames", [])) > 0]

        resp = self.asg.describe_launch_configurations(
            LaunchConfigurationNames=zeroed_lcs
        )

        amis = [lc.get("ImageId", "")
                for lc in resp.get("LaunchConfigurations", [])]

        return amis
    
    def fetch_zeroed_asg_lt(self):

        """
        Find AMIs for autoscaling groups who's desired capacity is set to 0
        """

        resp = self.asg.describe_auto_scaling_groups()
        # This does not support multiple versions of the same launch template being used
        zeroed_lts = [asg.get("LaunchTemplate", {})
                      for asg in resp.get("AutoScalingGroups", [])
                      if asg.get("DesiredCapacity", 0) == 0]

        zeroed_lt_names = [lt.get("LaunchTemplateName", "")
                        for lt in zeroed_lts]

        zeroed_lt_versions = [lt.get("LaunchTemplateVersion", "")
                        for lt in zeroed_lts]

        zeroed_lt_names = list(filter(None, zeroed_lt_names))
        resp = self.ec2.describe_launch_templates(
            LaunchTemplateNames=zeroed_lt_names
        )

        amis = []
        for lt_name, lt_version in zip(zeroed_lt_names, zeroed_lt_versions):
            resp = self.ec2.describe_launch_template_versions(
                LaunchTemplateName=lt_name
                # Cannot be empty... Versions=[lt_version] - unsure how to pass param only if present in Python 
            )
            amis += (lt_latest_version.get("LaunchTemplateData", {}).get("ImageId")
                        for lt_latest_version in resp.get("LaunchTemplateVersions", []))

        return amis

    def fetch_instances(self):

        """ Find AMIs for not terminated EC2 instances """

        resp = self.ec2.describe_instances(
            Filters=[
                {
                    'Name': 'instance-state-name',
                    'Values': [
                        'pending',
                        'running',
                        'shutting-down',
                        'stopping',
                        'stopped'
                    ]
                }
            ]
        )
        amis = [i.get("ImageId", None)
                for r in resp.get("Reservations", [])
                for i in r.get("Instances", [])]

        return amis
