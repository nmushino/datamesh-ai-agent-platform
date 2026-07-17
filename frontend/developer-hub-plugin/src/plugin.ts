import {
  createPlugin,
  createComponentExtension,
} from '@backstage/core-plugin-api';
import { rootRouteRef } from './routes';

export const kafkaTopicRequestPlugin = createPlugin({
  id: 'kafka-topic-request',
  routes: {
    root: rootRouteRef,
  },
});

export const KafkaTopicRequestContent = kafkaTopicRequestPlugin.provide(
  createComponentExtension({
    name: 'KafkaTopicRequestContent',
    component: {
      lazy: () =>
        import('./components/TopicRequestPage').then(
          m => m.TopicRequestContent,
        ),
    },
  }),
);
