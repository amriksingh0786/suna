#!/usr/bin/env python3
"""
Script to fix RabbitMQ queue configuration issues.
This script clears the problematic 'default' queue that has conflicting dead letter exchange settings.
"""

import pika
import os
import sys
from utils.logger import logger

def fix_rabbitmq_queue():
    """Clear the problematic default queue from RabbitMQ."""
    
    rabbitmq_host = os.getenv('RABBITMQ_HOST', 'localhost')
    rabbitmq_port = int(os.getenv('RABBITMQ_PORT', 5672))
    
    try:
        # Connect to RabbitMQ
        connection = pika.BlockingConnection(
            pika.ConnectionParameters(host=rabbitmq_host, port=rabbitmq_port)
        )
        channel = connection.channel()
        
        logger.info(f"Connected to RabbitMQ at {rabbitmq_host}:{rabbitmq_port}")
        
        # Delete the problematic 'default' queue
        try:
            channel.queue_delete(queue='default')
            logger.info("Successfully deleted the 'default' queue")
        except Exception as e:
            logger.warning(f"Could not delete 'default' queue (might not exist): {e}")
        
        # Delete any other problematic queues
        problematic_queues = ['default_DLX', 'default_failed']
        for queue_name in problematic_queues:
            try:
                channel.queue_delete(queue=queue_name)
                logger.info(f"Successfully deleted queue: {queue_name}")
            except Exception as e:
                logger.warning(f"Could not delete queue '{queue_name}' (might not exist): {e}")
        
        connection.close()
        logger.info("RabbitMQ queue cleanup completed successfully")
        return True
        
    except pika.exceptions.AMQPConnectionError as e:
        logger.error(f"Failed to connect to RabbitMQ: {e}")
        logger.error("Make sure RabbitMQ is running and accessible")
        return False
    except Exception as e:
        logger.error(f"Unexpected error while fixing RabbitMQ queues: {e}")
        return False

if __name__ == "__main__":
    success = fix_rabbitmq_queue()
    sys.exit(0 if success else 1) 